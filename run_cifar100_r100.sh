python $HOME/M2m/train.py --no_over  --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM' --warm 200 --epoch 200
python $HOME/M2m/train.py --ratio 100  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM_RS' --warm 0 --epoch 200
python $HOME/M2m/train.py -s --ratio 100  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM_SMOTE' --warm 0 --epoch 200
python $HOME/M2m/train.py --no_over -c  --eff_beta 1.0 --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM_RW' --warm 0 --epoch 200
python $HOME/M2m/train.py --no_over -c  --eff_beta 0.999 --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM_CBLoss' --warm 0 --epoch 200
python $HOME/M2m/train.py --ratio 100  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM_DRS' --warm 160 --epoch 200
python $HOME/M2m/train.py -gen -r --ratio 100  --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM_M2m' --beta 0.999 --lam 0.5 --gamma 0.9 --step_size 0.1 --attack_iter 10 --warm 160 --epoch 200 --net_g ./checkpoint/erm_cifar100_r100.t7
python $HOME/M2m/train.py --no_ove --loss_type Focal --focal_gamma 1.0 --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'Focal' --warm 160 --epoch 200
python $HOME/M2m/train.py --no_over -c --loss_type LDAM --eff_beta 0.999 --ratio 100 --decay 2e-4 --model resnet32_norm --dataset cifar100 --lr 0.1 --batch-size 128 --name 'LDAM-DRW' --warm 160 --epoch 200
python $HOME/M2m/train.py -gen -r --loss_type LDAM   --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'LDAM_M2m' --beta 0.999 --lam 0.5 --gamma 0.9 --step_size 0.1 --attack_iter 10 --warm 160 --epoch 200 --net_g ./checkpoint/erm_cifar100_r100.t7
