from __future__ import print_function
import argparse
import os
import numpy as np
import scipy.io as sio
from PIL import Image
import torchvision.transforms as TT

import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.optim
import torch.utils.data as DD

from C3D import *

parser = argparse.ArgumentParser(description='PyTorch Training')
# data
parser.add_argument('--mRGB', default=[101, 98, 90], type=float, nargs='+', dest='mRGB', help='mean RGB')
# model
parser.add_argument('--nClass', default=1, type=int, help='number of classes')
parser.add_argument('--dropRatio', default=0, type=float, help='dropout ratio')
parser.add_argument('--leak', default=0, type=float, help='leaky relu')
# evaluate
parser.add_argument('--model', default='/home/zwei/.torch/models/c3d_ucf101_params.mat', help='model to test')
parser.add_argument('--saveDir', default='/home/zwei/datasets/THUMOS14/features/c3d-dense', help='file to save results')
# misc

def mkdir_p(path):
    if not os.path.isdir(path):
        os.makedirs(path)

print('==> parsing options')
global opts
opts = parser.parse_args()
print(opts)
mkdir_p(opts.saveDir)

print('==> create model')
model = C3D(nClass=opts.nClass, dropRatio=opts.dropRatio, leak=opts.leak)
model.cuda().eval()

print('==> initialize model with [%s]'%(opts.model))
if opts.model[-4:]=='.mat':
    model._init_from_mat(opts.model, lastLayer=False)
elif os.path.isfile(opts.model):
    L = torch.load(opts.model)
    model.load_state_dict(L['state_dict'])
else:
    print('[%s] not found'%(opts.model))
    quit()

print('==> register forward hook functions')
Buffer = {}
def _relu6_hook(self, input, output):
    Buffer['relu6'] = output.data.clone()
model.relu6.register_forward_hook(_relu6_hook)

print('==> obtain the list of video ids for THUMOS14 dataset')
L = sio.loadmat('anno_instances.mat')
val_videos = L['val'][0,0][0]
tst_videos = L['tst'][0,0][0]
val_videos = [val_videos[i,0][0] for i in range(len(val_videos))]
tst_videos = [tst_videos[i,0][0] for i in range(len(tst_videos))]
all_videos = sorted(list(set(val_videos + tst_videos)))

# scale, crop-center
H, W = [128, 176]
H_, W_ = [112, 112]
crp = [H/2-H_/2, H/2+H_/2-1, W/2-W_/2, W/2+W_/2-1]
CLIP = torch.zeros(3, 16, H_, W_)
toTensor = TT.ToTensor()
frame_directories = '/home/zwei/datasets/THUMOS14/frame'
print('==> start extracting features')
for i in range(len(all_videos)):
    print(i)
    video = all_videos[i]
    matFile = os.path.join(opts.saveDir, '{:s}.mat'.format(video))
    # matFile = '%s/%s.mat'%(opts.saveDir, video)
    if not os.path.isfile(matFile):
        frameDir = os.path.join(frame_directories, video)
        maxFrm = len(os.listdir(frameDir))
        nseg = int(round(maxFrm/16.0))
        relu6 = torch.zeros(nseg, 4096)

        for seg in range(nseg):
            for t in range(16):
                indice = seg*16+t+1
                im = Image.open('%s/i_%06d.jpg'%(frameDir, min(indice, maxFrm)))
                im = im.resize((W, H), Image.BILINEAR)
                im = im.crop((crp[2], crp[0], crp[3]+1, crp[1]+1)) # left-inclusive, [a, b)
                im = toTensor(im)
                CLIP[:,t,:,:].copy_(im)
            CLIP = CLIP*255
            CLIP = CLIP - torch.Tensor(opts.mRGB).view(3,1,1,1)
        
            inputs = Variable(CLIP.unsqueeze(0).cuda(), volatile=True)
            model.forward(inputs)
            relu6[seg].copy_(Buffer['relu6'][0])

        sio.savemat(matFile, {'relu6':relu6.numpy()})
