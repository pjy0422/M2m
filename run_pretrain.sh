python $HOME/M2m/train.py --no_over  --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM' --warm 200 --epoch 200
python $HOME/M2m/train.py --no_over  --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar10 --lr 0.1 --batch-size 128 --name 'ERM' --warm 200 --epoch 200
python $HOME/M2m/train.py --no_over  --ratio 100 --decay 2e-4 --model resnet32 --dataset cifar10 --lr 0.1 --batch-size 128 --name 'ERM' --warm 200 --epoch 200
python $HOME/M2m/train.py --no_over  --ratio 10 --decay 2e-4 --model resnet32 --dataset cifar100 --lr 0.1 --batch-size 128 --name 'ERM' --warm 200 --epoch 200
