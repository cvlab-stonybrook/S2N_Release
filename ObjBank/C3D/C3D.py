import math
import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.nn.functional as FF
import numpy as np
import scipy.io as sio

def conv3d(in_planes, out_planes, kernel_size=3, stride=1, leak=0):
    return nn.Sequential(
        nn.Conv3d(in_planes, out_planes, kernel_size=kernel_size, stride=stride, padding=(kernel_size-1)//2, bias=True),
        nn.LeakyReLU(leak, inplace=True)
    )

def pool3d(kernel_size=(2,2,2)):
    return nn.MaxPool3d(kernel_size=kernel_size, stride=kernel_size, ceil_mode=True)

class C3D(nn.Module):
    def __init__(self, nClass=13, dropRatio=0.5, leak=0):
        super(C3D, self).__init__()

        self.conv1 = conv3d(3, 64, leak=leak)
        self.pool1 = pool3d((1,2,2))

        self.conv2 = conv3d(64, 128, leak=leak)
        self.pool2 = pool3d((2,2,2))

        self.conv3a = conv3d(128, 256, leak=leak)
        self.conv3b = conv3d(256, 256, leak=leak)
        self.pool3  = pool3d((2,2,2))

        self.conv4a = conv3d(256, 512, leak=leak)
        self.conv4b = conv3d(512, 512, leak=leak)
        self.pool4  = pool3d((2,2,2))

        self.conv5a = conv3d(512, 512, leak=leak)
        self.conv5b = conv3d(512, 512, leak=leak)
        self.pool5  = pool3d((2,2,2))

        self.full6 = nn.Linear(512*1*4*4, 4096)
        self.relu6 = nn.LeakyReLU(leak, inplace=True)
        
        self.drop7 = nn.Dropout(p=dropRatio)
        self.full7 = nn.Linear(4096, 4096)
        self.relu7 = nn.LeakyReLU(leak, inplace=True)
        
        self.drop8 = nn.Dropout(p=dropRatio)
        self.full8 = nn.Linear(4096, nClass)
        
        print("model not yet initialized")

    def _init_from_mat(self,  matfile='../c3d-init/C3D@Sport1M/params.mat', lastLayer=False):
        L = sio.loadmat(matfile)
        params = L['params']
        conv_layers = [ m for m in self.modules() if isinstance(m, nn.Conv3d) ]
        lin_layers = [ m for m in self.modules() if isinstance(m, nn.Linear) ]
        p = 0
        for m in conv_layers:
            m.weight.data.copy_(torch.from_numpy(params[p, 0]))
            p += 1
            m.bias.data.copy_(torch.from_numpy(params[p, 0]))
            p += 1
        for m in lin_layers[:-1]:
            m.weight.data.copy_(torch.from_numpy(params[p, 0]))
            p += 1
            m.bias.data.copy_(torch.from_numpy(params[p, 0]))
            p += 1
        if lastLayer:
            lin_layers[-1].weight.data.copy_(torch.from_numpy(params[p, 0]))
            lin_layers[-1].bias.data.copy_(torch.from_numpy(params[p+1, 0]))
        else:
            lin_layers[-1].weight.data.normal_(0, 0.01)
            lin_layers[-1].bias.data.fill_(0)

    def forward(self, x):
        [B, F, T, H, W] = x.size()
        assert(F==3 and T==16 and H==112 and W==112)
        pool1 = self.pool1(self.conv1(x))
        pool2 = self.pool2(self.conv2(pool1))
        pool3 = self.pool3(self.conv3b(self.conv3a(pool2)))
        pool4 = self.pool4(self.conv4b(self.conv4a(pool3)))
        pool5 = self.pool5(self.conv5b(self.conv5a(pool4)))
        pool5 = pool5.view(B, 512*1*4*4)
        relu6 = self.relu6(self.full6(pool5))
        relu7 = self.relu7(self.full7(self.drop7(relu6)))
        prob = self.full8(self.drop8(relu7))
        return prob

if __name__ == '__main__':
    model = C3D(nClass=13, dropRatio=0.5, leak=0)
    model._init_from_mat('../c3d-init/C3D@Sport1M/params.mat', lastLayer=False)
    x = Variable(torch.Tensor(2, 3, 16, 112, 112), volatile=True)
    y = model.cuda()(x.cuda())
    print(x.size(), y.size())
