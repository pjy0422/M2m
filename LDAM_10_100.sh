#!/bin/bash

#SBATCH --job-name=preL_10_100                  # Job 이름
#SBATCH --gres=gpu:1                      # Job에 사용할 리소스 (GPU)
#SBATCH --ntasks=8
#SBATCH -t 24:00:00  # 24 hour              # 이 job이 리소스를 물고 있을 최대 시간
#SBATCH --output=output_L_10_100.txt

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

hostname  # 무슨 노드에 배치됐는지 표시
python $HOME/M2m/train.py --no_over --eff_beta 0.999 -c -gen -r --loss_type LDAM   --ratio 100 --decay 2e-4 --model resnet32_norm --dataset cifar10 --lr 0.1 --batch-size 128 --name 'LDAM_M2m' --beta 0.999 --lam 0.5 --gamma 0.9 --step_size 0.1 --attack_iter 10 --warm 160 --epoch 200 --net_g /home/pjy0422/M2m/logs/Imbalance_S9916_LDAM-DRW_L0.5_W160_E0.1_I10_cifar10_R100_resnet32_norm_G0.99_B0.999/ckpt_9916.t7
conda deactivate
exit 0  # explicit 하게 job을 끝내 잠재적인 completing 문제가 생기는 것을 방지