#!/bin/bash
#SBATCH --job-name=100_10
#SBATCH --gres=gpu:1
#SBATCH --ntasks=8
#SBATCH --output=100_10.out

#SBATCH -t 24:00:00  # 24 hour              # 이 job이 리소스를 물고 있을 최대 시간
# 여기까지 마스터에서 실행
####################################################
# 여기부터 할당된 노드에서 실행됨
####################################################
export PATH="$PATH:/home/pjy0422/anaconda3/bin"
# User specific aliases and functions

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/pjy0422/anaconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/home/pjy0422/anaconda3/etc/profile.d/conda.sh" ]; then
        . "/home/pjy0422/anaconda3/etc/profile.d/conda.sh"
    else
        export PATH="/home/pjy0422/anaconda3/bin:$PATH"
    fi
fi
unset __conda_setup
conda activate venv_312
# module load cuda-11.8  # SPACK 세팅이 된 경우 CUDA runtime을 불러올 수 있음
python $HOME/M2m/train.py --no_over  --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM' --warm 200 --epoch 200
python $HOME/M2m/train.py --ratio 10  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM-RS' --warm 0 --epoch 200
python $HOME/M2m/train.py -s --ratio 10  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM-SMOTE' --warm 0 --epoch 200
python $HOME/M2m/train.py --no_over -c  --eff_beta 1.0 --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM-RW' --warm 0 --epoch 200
python $HOME/M2m/train.py --no_over -c  --eff_beta 0.999 --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM-CBLoss' --warm 0 --epoch 200
python $HOME/M2m/train.py --ratio 10  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM-DRS' --warm 160 --epoch 200
python $HOME/M2m/train.py -gen -r --ratio 10  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM-M2m' --beta 0.999 --lam 0.5 --gamma 0.9 --step_size 0.1 --attack_iter 10 --warm 160 --epoch 200 --net_g $HOME/M2m/checkpoint/ERM_resnet32_cifar100_10.t7
python $HOME/M2m/train.py --no_over --loss_type Focal --focal_gamma 1.0 --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'Focal' --warm 160 --epoch 200
python $HOME/M2m/train.py --no_over -c --loss_type LDAM --eff_beta 0.999 --ratio 10 --decay 2e-4 --model resnet32_norm --dataset cifar100 --lr 0.1 --batch-size 128 --name 'LDAM' --warm 0 --epoch 200
python $HOME/M2m/train.py --no_over -c --loss_type LDAM --eff_beta 0.999 --ratio 10 --decay 2e-4 --model resnet32_norm --dataset cifar100 --lr 0.1 --batch-size 128 --name 'LDAM-DRW' --warm 160 --epoch 200
python $HOME/M2m/train.py -gen -r -c --loss_type LDAM  --eff_beta 0.999  --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'LDAM-DRW-M2m' --beta 0.999 --lam 0.5 --gamma 0.9 --step_size 0.1 --attack_iter 10 --warm 160 --epoch 200 --net_g $HOME/M2m/checkpoint/LDAM-DRW_resnet32_norm_cifar100_10.t7

hostname  # 무슨 노드에 배치됐는지 표시
conda deactivate
exit 0  # explicit 하게 job을 끝내 잠재적인 completing 문제가 생기는 것을 방지