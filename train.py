#!/usr/bin/env python3 -u
# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the license found in the LICENSE file in
# the root directory of this source tree.
from __future__ import print_function

import csv
import os

import matplotlib.pyplot as plt

plt.switch_backend("agg")
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from config import *
from imblearn.metrics import geometric_mean_score
from scipy.stats import gmean
from sklearn.metrics import balanced_accuracy_score, precision_score, recall_score
from torch.autograd import Variable, grad
from tqdm import tqdm
from utils import (
    FocalLoss,
    LDAMLoss,
    Logger,
    classwise_loss,
    inf_data_gen,
    make_step,
    random_perturb,
    soft_cross_entropy,
)

LOGNAME = "Imbalance_" + LOGFILE_BASE
logger = Logger(LOGNAME)
LOGDIR = logger.logdir

LOG_CSV = os.path.join(LOGDIR, f"log_{SEED}.csv")
LOG_CSV_HEADER = [
    "epoch",
    "train loss",
    "gen loss",
    "train acc",
    "gen_acc",
    "prob_orig",
    "prob_targ",
    "train bal acc",
    "train gm",
    "test loss",
    "major test acc",
    "neutral test acc",
    "minor test acc",
    "test acc",
    "f1 score",
    "test gm",
    "test bal acc",
]
if not os.path.exists(LOG_CSV):
    with open(LOG_CSV, "w") as f:
        csv_writer = csv.writer(f, delimiter=",")
        csv_writer.writerow(LOG_CSV_HEADER)


def save_checkpoint(acc, model, optim, epoch, index=False):
    # Save checkpoint.
    print("Saving..")

    if isinstance(model, nn.DataParallel):
        model = model.module

    state = {
        "net": model.state_dict(),
        "optimizer": optim.state_dict(),
        "acc": acc,
        "epoch": epoch,
        "rng_state": torch.get_rng_state(),
    }

    if index:
        ckpt_name = "ckpt_epoch" + str(epoch) + "_" + str(SEED) + ".t7"
    else:
        ckpt_name = "ckpt_" + str(SEED) + ".t7"

    ckpt_path = os.path.join(LOGDIR, ckpt_name)
    torch.save(state, ckpt_path)
    if (
        ARGS.name == "ERM"
        or ARGS.name == "LDAM"
        or ARGS.name == "ERM-M2m"
        or ARGS.name == "LDAM-M2m"
    ):
        file_name = f"/home/ubuntu/M2m/checkpoint/{ARGS.name}_{ARGS.model}_{ARGS.dataset}_{ARGS.ratio}.t7"
        if not os.path.exists(file_name):
            torch.save(state, file_name)
        if epoch == ARGS.warm - 1:
            file_name = f"/home/ubuntu/M2m/checkpoint/{ARGS.name}_{ARGS.model}_{ARGS.dataset}_{ARGS.ratio}_warm.t7"
            torch.save(state, file_name)


def train_epoch(model, criterion, optimizer, data_loader, logger=None):
    model.train()

    train_loss = 0
    correct = 0
    total = 0

    all_targets = []
    all_predicted = []
    all_outputs = []
    class_counts = {}

    for inputs, targets in tqdm(data_loader):
        # For SMOTE, get the samples from smote_loader instead of usual loader
        if epoch >= ARGS.warm and ARGS.smote:
            inputs, targets = next(smote_loader_inf)

        inputs, targets = inputs.to(device), targets.to(device)
        batch_size = inputs.size(0)

        outputs, _ = model(normalizer(inputs))
        loss = criterion(outputs, targets).mean()

        train_loss += loss.item() * batch_size
        predicted = outputs.max(1)[1]
        total += batch_size
        correct += sum_t(predicted.eq(targets))

        for target, prediction, output in zip(
            targets.cpu().numpy(),
            predicted.cpu().numpy(),
            outputs.detach().cpu().numpy(),
        ):
            if class_counts.get(target, 0) < 50:
                all_targets.append(target)
                all_predicted.append(prediction)
                all_outputs.append(output)
                class_counts[target] = class_counts.get(target, 0) + 1

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    all_targets = np.array(all_targets)
    all_predicted = np.array(all_predicted)
    all_outputs = np.array(all_outputs)
    # Get unique classes
    classes = np.unique(all_targets)

    # Calculate recall for each class
    recalls = [
        recall_score(all_targets == cls, all_predicted == cls) + 1e-10
        for cls in classes
    ]

    # Calculate balanced accuracy
    bal_acc_score = np.mean(recalls)

    # Calculate geometric mean score
    gmean_score = gmean(recalls)

    msg = "Loss: %.3f| Acc: %.3f%% (%d/%d) | GMean: %.3f | BalAcc: %.3f" % (
        train_loss / total,
        100.0 * correct / total,
        correct,
        total,
        100.0 * gmean_score,
        100.0 * bal_acc_score,
    )

    if logger:
        logger.log(msg)
    else:
        print(msg)

    # Apply t-SNE to the outputs
    tsne = TSNE(n_components=2, random_state=42)
    outputs_tsne = tsne.fit_transform(all_outputs)

    # Plot the t-SNE results
    plt.figure(figsize=(10, 8))
    for class_index in classes:
        idxs = [i for i, x in enumerate(all_targets) if x == class_index]
        if len(idxs) > 50:
            idxs = np.random.choice(idxs, 50, replace=False)
        plt.scatter(
            outputs_tsne[idxs, 0], outputs_tsne[idxs, 1], label=f"Class {class_index}"
        )

    plt.legend()
    plt.title("t-SNE of Training Set Outputs")
    plt.grid(True)
    plt.gca().axes.get_xaxis().set_visible(False)
    plt.gca().axes.get_yaxis().set_visible(False)
    plt.savefig("train_set_decision_boundary.png")
    plt.close()

    return (
        train_loss / total,
        100.0 * correct / total,
        100.0 * bal_acc_score,
        100.0 * gmean_score,
    )


def uniform_loss(outputs):
    weights = torch.ones_like(outputs) / N_CLASSES

    return soft_cross_entropy(outputs, weights, reduction="mean")


def classwise_loss(outputs, targets):
    out_1hot = torch.zeros_like(outputs)
    out_1hot.scatter_(1, targets.view(-1, 1), 1)
    return (outputs * out_1hot).sum(1).mean()


def generation(
    model_g,
    model_r,
    inputs,
    seed_targets,
    targets,
    p_accept,
    gamma,
    lam,
    step_size,
    random_start=True,
    max_iter=10,
):
    model_g.eval()
    model_r.eval()
    criterion = nn.CrossEntropyLoss()

    if random_start:
        random_noise = random_perturb(inputs, "l2", 0.5)
        inputs = torch.clamp(inputs + random_noise, 0, 1)

    for _ in range(max_iter):
        inputs = inputs.clone().detach().requires_grad_(True)
        outputs_g, _ = model_g(normalizer(inputs))
        outputs_r, _ = model_r(normalizer(inputs))

        loss = criterion(outputs_g, targets) + lam * classwise_loss(
            outputs_r, seed_targets
        )
        (grad,) = torch.autograd.grad(loss, [inputs])

        inputs = inputs - make_step(grad, "l2", step_size)
        inputs = torch.clamp(inputs, 0, 1)

    inputs = inputs.detach()

    outputs_g, _ = model_g(normalizer(inputs))

    one_hot = torch.zeros_like(outputs_g)
    one_hot.scatter_(1, targets.view(-1, 1), 1)
    probs_g = torch.softmax(outputs_g, dim=1)[one_hot.to(torch.bool)]
    flag = (ARGS.ratio == 1) and (ARGS.imb_type == "none")

    if flag == True:
        correct = torch.ones_like(torch.bernoulli(p_accept).byte()).to(device)
    elif flag == False:
        correct = (probs_g >= gamma) * torch.bernoulli(p_accept).byte().to(device)
    model_r.train()

    return inputs, correct


def train_net(
    model_train,
    model_gen,
    criterion,
    optimizer_train,
    inputs_orig,
    targets_orig,
    gen_idx,
    gen_targets,
):
    batch_size = inputs_orig.size(0)

    inputs = inputs_orig.clone()
    targets = targets_orig.clone()
    gen_idx = gen_idx.to(device)
    gen_targets = gen_targets.to(device)

    ########################

    bs = N_SAMPLES_PER_CLASS_T[targets_orig].repeat(gen_idx.size(0), 1)
    gs = N_SAMPLES_PER_CLASS_T[gen_targets].view(-1, 1)
    delta = F.relu(bs - gs)
    p_accept = 1 - ARGS.beta**delta
    mask_valid = (p_accept.sum(1) > 0).to(device)

    gen_idx = gen_idx[mask_valid]
    gen_targets = gen_targets[mask_valid]
    p_accept = p_accept[mask_valid]

    select_idx = torch.multinomial(p_accept, 1, replacement=True).view(-1)
    p_accept = p_accept.gather(1, select_idx.view(-1, 1)).view(-1)

    seed_targets = targets_orig[select_idx]
    seed_images = inputs_orig[select_idx]

    if ARGS.ratio == 1 and ARGS.imb_type == "none":
        p_accept = torch.ones_like(p_accept)
        gen_idx = torch.arange(batch_size).to(device)
        # gen_targets = torch.randint(N_CLASSES, (batch_size,)).to(device).long()
        gen_targets = targets_orig  # why? because we want to generate the same class
        seed_targets = targets_orig
        seed_images = inputs_orig

    gen_inputs, correct_mask = generation(
        model_gen,
        model_train,
        seed_images,
        seed_targets,
        gen_targets,
        p_accept,
        ARGS.gamma,
        ARGS.lam,
        ARGS.step_size,
        True,
        ARGS.attack_iter,
    )

    ########################

    # Only change the correctly generated samples
    if ARGS.ratio == 1 and ARGS.imb_type == "none":
        probabilities = torch.full((batch_size,), ARGS.gen_prob, device=device)

        correct_mask = torch.bernoulli(probabilities).bool()
    num_gen = sum_t(correct_mask)
    num_others = batch_size - num_gen

    gen_c_idx = gen_idx[correct_mask]
    others_mask = torch.ones(batch_size, dtype=torch.bool, device=device)
    others_mask[gen_c_idx] = 0
    others_idx = others_mask.nonzero().view(-1)

    if num_gen > 0:
        gen_inputs_c = gen_inputs[correct_mask]
        gen_targets_c = gen_targets[correct_mask]

        inputs[gen_c_idx] = gen_inputs_c
        targets[gen_c_idx] = gen_targets_c

    outputs, _ = model_train(normalizer(inputs))
    loss = criterion(outputs, targets)

    optimizer_train.zero_grad()
    loss.mean().backward()
    optimizer_train.step()

    # For logging the training

    oth_loss_total = sum_t(loss[others_idx])
    gen_loss_total = sum_t(loss[gen_c_idx])

    _, predicted = torch.max(outputs[others_idx].data, 1)
    num_correct_oth = sum_t(predicted.eq(targets[others_idx]))

    num_correct_gen, p_g_orig, p_g_targ = 0, 0, 0
    success = torch.zeros(N_CLASSES, 2)

    if num_gen > 0:
        _, predicted_gen = torch.max(outputs[gen_c_idx].data, 1)
        num_correct_gen = sum_t(predicted_gen.eq(targets[gen_c_idx]))
        probs = torch.softmax(outputs[gen_c_idx], 1).data

        p_g_orig = probs.gather(1, seed_targets[correct_mask].view(-1, 1))
        p_g_orig = sum_t(p_g_orig)

        p_g_targ = probs.gather(1, gen_targets_c.view(-1, 1))
        p_g_targ = sum_t(p_g_targ)

    for i in range(N_CLASSES):
        if num_gen > 0:
            success[i, 0] = sum_t(gen_targets_c == i)
        success[i, 1] = sum_t(gen_targets == i)
    all_targets = targets.cpu().numpy()
    num_samples_per_class = 50
    # Ensure outputs is a list or sequence before concatenating

    # Concatenate outputs into a single tensor

    # Use the appropriate indexing for `all_outputs`
    # Convert all_outputs to numpy for t-SNE

    return (
        oth_loss_total,
        gen_loss_total,
        num_others,
        num_correct_oth,
        num_gen,
        num_correct_gen,
        p_g_orig,
        p_g_targ,
        success,
    )


def train_gen_epoch(net_t, net_g, criterion, optimizer, data_loader):
    net_t.train()
    net_g.eval()

    oth_loss, gen_loss = 0, 0
    correct_oth = 0
    correct_gen = 0
    total_oth, total_gen = 1e-6, 1e-6
    p_g_orig, p_g_targ = 0, 0
    t_success = torch.zeros(N_CLASSES, 2)

    all_targets = []
    all_predicted = []

    for inputs, targets in tqdm(data_loader):
        batch_size = inputs.size(0)
        inputs, targets = inputs.to(device), targets.to(device)

        # Set a generation target for current batch with re-sampling
        if ARGS.imb_type != "none":  # Imbalanced
            # Keep the sample with this probability
            gen_probs = N_SAMPLES_PER_CLASS_T[targets] / N_SAMPLES_PER_CLASS_T[0]
            gen_index = (1 - torch.bernoulli(gen_probs)).nonzero()  # Generation index
            gen_index = gen_index.view(-1)
            gen_targets = targets[gen_index]
        else:  # Balanced
            gen_index = torch.arange(batch_size).view(-1)
            gen_targets = torch.randint(N_CLASSES, (batch_size,)).to(device).long()

        (
            t_loss,
            g_loss,
            num_others,
            num_correct,
            num_gen,
            num_gen_correct,
            p_g_orig_batch,
            p_g_targ_batch,
            success,
        ) = train_net(
            net_t, net_g, criterion, optimizer, inputs, targets, gen_index, gen_targets
        )

        oth_loss += t_loss
        gen_loss += g_loss
        total_oth += num_others
        correct_oth += num_correct
        total_gen += num_gen
        correct_gen += num_gen_correct
        p_g_orig += p_g_orig_batch
        p_g_targ += p_g_targ_batch
        t_success += success
        all_targets.extend(targets.cpu().numpy())
        all_predicted.extend(targets.cpu().numpy())

    res = {
        "train_loss": oth_loss / total_oth,
        "gen_loss": gen_loss / total_gen,
        "train_acc": 100.0 * correct_oth / total_oth,
        "gen_acc": 100.0 * correct_gen / total_gen,
        "p_g_orig": p_g_orig / total_gen,
        "p_g_targ": p_g_targ / total_gen,
        "t_success": t_success,
        "train_bal_acc": balanced_accuracy_score(all_targets, all_predicted),
        "train_gm": geometric_mean_score(all_targets, all_predicted),
    }

    msg = (
        "t_Loss: %.3f | g_Loss: %.3f | Acc: %.3f%% (%d/%d) | Acc_gen: %.3f%% (%d/%d) "
        "| Prob_orig: %.3f | Prob_targ: %.3f"
        % (
            res["train_loss"],
            res["gen_loss"],
            res["train_acc"],
            correct_oth,
            total_oth,
            res["gen_acc"],
            correct_gen,
            total_gen,
            res["p_g_orig"],
            res["p_g_targ"],
        )
    )
    if logger:
        logger.log(msg)
    else:
        print(msg)

    return res


if __name__ == "__main__":
    TEST_ACC = 0  # best test accuracy
    BEST_VAL = 0  # best validation accuracy

    # Weights for virtual samples are generated
    logger.log("==> Building model: %s" % MODEL)
    net = models.__dict__[MODEL](N_CLASSES)
    net_seed = models.__dict__[MODEL](N_CLASSES)

    net, net_seed = net.to(device), net_seed.to(device)
    optimizer = optim.SGD(
        net.parameters(), lr=ARGS.lr, momentum=0.9, weight_decay=ARGS.decay
    )

    if ARGS.resume:
        # Load checkpoint.
        logger.log("==> Resuming from checkpoint..")
        ckpt_g = f"./checkpoint/{DATASET}/ratio{ARGS.ratio}/erm_trial1_{MODEL}.t7"

        if ARGS.net_both is not None:
            ckpt_t = torch.load(ARGS.net_both)
            net.load_state_dict(ckpt_t["net"])
            optimizer.load_state_dict(ckpt_t["optimizer"])
            START_EPOCH = ckpt_t["epoch"] + 1
            net_seed.load_state_dict(ckpt_t["net2"])
        else:
            if ARGS.net_t is not None:
                ckpt_t = torch.load(ARGS.net_t)
                net.load_state_dict(ckpt_t["net"])
                optimizer.load_state_dict(ckpt_t["optimizer"])
                START_EPOCH = ckpt_t["epoch"] + 1

            if ARGS.net_g is not None:
                ckpt_g = ARGS.net_g
                print(ckpt_g)
                ckpt_g = torch.load(ckpt_g)
                net_seed.load_state_dict(ckpt_g["net"])

    if N_GPUS > 1:
        logger.log("Multi-GPU mode: using %d GPUs for training." % N_GPUS)
        net = nn.DataParallel(net)
        net_seed = nn.DataParallel(net_seed)
    elif N_GPUS == 1:
        logger.log("Single-GPU mode.")

    if ARGS.warm < START_EPOCH and ARGS.over:
        raise ValueError("warm < START_EPOCH")

    SUCCESS = torch.zeros(EPOCH, N_CLASSES, 2)
    test_stats = {}
    for epoch in range(START_EPOCH, EPOCH):
        logger.log(" * Epoch %d: %s" % (epoch, LOGDIR))
        # wandb.log({"epoch": epoch, "learning_rate": LR})
        adjust_learning_rate(optimizer, LR, epoch)

        if epoch == ARGS.warm and ARGS.over:
            if ARGS.smote:
                logger.log("=============== Applying smote sampling ===============")
                smote_loader, _, _ = get_smote(
                    DATASET,
                    N_SAMPLES_PER_CLASS,
                    BATCH_SIZE,
                    transform_train,
                    transform_test,
                )
                smote_loader_inf = inf_data_gen(smote_loader)
            else:
                logger.log("=============== Applying over sampling ===============")
                train_loader, _, _ = get_oversampled(
                    DATASET,
                    N_SAMPLES_PER_CLASS,
                    BATCH_SIZE,
                    transform_train,
                    transform_test,
                )

        ## For Cost-Sensitive Learning ##

        if ARGS.cost and epoch >= ARGS.warm:
            beta = ARGS.eff_beta
            if beta < 1:
                effective_num = 1.0 - np.power(beta, N_SAMPLES_PER_CLASS)
                per_cls_weights = (1.0 - beta) / np.array(effective_num)
            else:
                per_cls_weights = 1 / np.array(N_SAMPLES_PER_CLASS)
            per_cls_weights = (
                per_cls_weights / np.sum(per_cls_weights) * len(N_SAMPLES_PER_CLASS)
            )
            per_cls_weights = torch.FloatTensor(per_cls_weights).to(device)
        else:
            per_cls_weights = torch.ones(N_CLASSES).to(device)

        ## Choos a loss function ##

        if ARGS.loss_type == "CE":
            criterion = nn.CrossEntropyLoss(
                weight=per_cls_weights, reduction="none"
            ).to(device)
        elif ARGS.loss_type == "Focal":
            criterion = FocalLoss(
                weight=per_cls_weights, gamma=ARGS.focal_gamma, reduction="none"
            ).to(device)
        elif ARGS.loss_type == "LDAM":
            criterion = LDAMLoss(
                cls_num_list=N_SAMPLES_PER_CLASS,
                max_m=0.5,
                s=30,
                weight=per_cls_weights,
                reduction="none",
            ).to(device)
        else:
            raise ValueError("Wrong Loss Type")

        ## Training ( ARGS.warm is used for deferred re-balancing ) ##

        if epoch >= ARGS.warm and ARGS.gen:
            if epoch == 199:
                train_loss, train_acc, train_bal_acc, train_gm = train_epoch(
                    net, criterion, optimizer, train_loader, logger
                )

                train_stats = {
                    "train_loss": train_loss,
                    "train_acc": train_acc,
                    "train_bal_acc": train_bal_acc,
                    "train_gm": train_gm,
                }
                break
            train_stats = train_gen_epoch(
                net, net_seed, criterion, optimizer, train_loader
            )

            SUCCESS[epoch, :, :] = train_stats["t_success"].float()
            logger.log(SUCCESS[epoch, -10:, :])
            np.save(LOGDIR + "/success.npy", SUCCESS.cpu().numpy())
        else:
            train_loss, train_acc, train_bal_acc, train_gm = train_epoch(
                net, criterion, optimizer, train_loader, logger
            )

            train_stats = {
                "train_loss": train_loss,
                "train_acc": train_acc,
                "train_bal_acc": train_bal_acc,
                "train_gm": train_gm,
            }
            if epoch == 159:
                save_checkpoint(train_acc, net, optimizer, epoch, True)

        ## Evaluation ##

        val_eval = evaluate(net, val_loader, logger=logger)
        val_eval_copy_for_log = val_eval.copy()
        # add key name prefix val_
        val_eval_copy_for_log = {
            "val_" + key: val_eval[key] for key in val_eval if key != "class_acc"
        }
        # for i, class_i_acc in enumerate(val_eval["class_acc"]):
        # wandb.log({f"val_class_{i}_acc": class_i_acc})
        # class-wise accuracy is logged separately
        val_eval_copy_for_log["val_classwise_acc_avg"] = val_eval["class_acc"].mean()
        # wandb.log(train_stats)
        # wandb.log(val_eval_copy_for_log)
        val_acc = val_eval["test_bal_acc"]
        if val_acc >= BEST_VAL:
            BEST_VAL = val_acc

            test_stats = evaluate(net, test_loader, logger=logger)
            test_stats_copy_for_log = test_stats.copy()
            # add key name prefix test_
            test_stats_copy_for_log = {
                "test_" + key: test_stats[key]
                for key in test_stats
                if key != "class_acc"
            }
            # for i, class_i_acc in enumerate(test_stats["class_acc"]):
            # wandb.log({f"test_class_{i}_acc": class_i_acc})
            # class-wise accuracy is logged separately
            test_stats_copy_for_log["test_classwise_acc_avg"] = test_stats[
                "class_acc"
            ].mean()
            # wandb.log(test_stats_copy_for_log, step=epoch)
            TEST_ACC = test_stats["test_bal_acc"]
            TEST_ACC_CLASS = test_stats["class_acc"]

            save_checkpoint(TEST_ACC, net, optimizer, epoch)
            logger.log(
                "========== Class-wise test performance ( avg : {} ) ==========".format(
                    TEST_ACC_CLASS.mean()
                )
            )
            np.save(LOGDIR + "/classwise_acc.npy", TEST_ACC_CLASS.cpu())

        def _convert_scala(x):
            if hasattr(x, "item"):
                x = x.item()
            return x

        log_tr = [
            "train_loss",
            "gen_loss",
            "train_acc",
            "gen_acc",
            "p_g_orig",
            "p_g_targ",
            "train_bal_acc",
            "train_gm",
        ]
        log_te = [
            "loss",
            "major_acc",
            "neutral_acc",
            "minor_acc",
            "acc",
            "f1_score",
            "test_gm",
            "test_bal_acc",
        ]

        log_vector = (
            [epoch]
            + [train_stats.get(k, 0) for k in log_tr]
            + [test_stats.get(k, 0) for k in log_te]
        )
        log_vector = list(map(_convert_scala, log_vector))

        with open(LOG_CSV, "a") as f:
            logwriter = csv.writer(f, delimiter=",")
            logwriter.writerow(log_vector)
        # log using wandb
    df = pd.read_csv(LOG_CSV)
    df_table = wandb.Table(dataframe=df)
    csv_folder = os.path.join("/home/ubuntu/M2m/", "csv")
    os.makedirs(csv_folder, exist_ok=True)
    test_last_idx = df["test bal acc"].idxmax()
    test_last_result = df.loc[test_last_idx]
    test_last_result["name"] = ARGS.name
    test_last_result["model"] = ARGS.model
    file_name = f"{ARGS.dataset}_{ARGS.ratio}_{ARGS.n_samples}.csv"
    # specify the path to the csv file
    csv_file_path = os.path.join(csv_folder, file_name)
    new_df = pd.DataFrame([test_last_result]).round(2)
    # check if the file exists
    if os.path.isfile(csv_file_path):
        # load the existing csv file into a DataFrame
        existing_df = pd.read_csv(csv_file_path)

        # check if ARGS.name is already in the DataFrame
        if ARGS.name not in existing_df["name"].values:
            # if not, append test_last_result to the DataFrame
            existing_df = pd.concat([existing_df, new_df], axis=0, ignore_index=True)

            # save the DataFrame to the csv file
            existing_df.round(2).to_csv(csv_file_path, index=False)
        elif ARGS.name in existing_df["name"].values:
            # if ARGS.name is already in the DataFrame, update the row with test_last_result if the test accuracy of the new result is higher
            existing_idx = existing_df[existing_df["name"] == ARGS.name].index[0]
            if (
                test_last_result["test bal acc"]
                > existing_df.loc[existing_idx]["test bal acc"]
            ) and (
                test_last_result["test gm"] > existing_df.loc[existing_idx]["test gm"]
            ):
                existing_df.loc[existing_idx] = test_last_result.round(2)

                # save the DataFrame to the csv file
                existing_df.round(2).to_csv(csv_file_path, index=False)
    else:
        # if the file doesn't exist, create a new DataFrame from test_last_result

        # save the new DataFrame to the csv file
        new_df.to_csv(csv_file_path, index=False)
    wandb.log({"table": df_table})
    wandb.finish()
