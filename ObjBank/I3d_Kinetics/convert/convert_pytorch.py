import argparse
import os
import sys

import h5py
import torch

project_root = os.path.join(os.path.expanduser('~'), 'Dev/VideoSum')
sys.path.append(project_root)
from I3d_Kinetics.I3D_Pytorch import I3D


######################################################################
## Load parameters from HDF5 to Dict
######################################################################

def load_conv3d(state_dict, modality, dump_dir, name_pth, name_tf):
    h5f = h5py.File(dump_dir + modality + "/" + name_tf + "/" + name_tf.split('/')[-1] + '.h5', 'r')

    # weight need (out_channel, in_channel, L, H, W)
    weight = torch.from_numpy(h5f['weights'][()]).permute(4, 3, 0, 1, 2)
    out_planes = weight.size(0)
    gamma = torch.ones(out_planes)
    beta = torch.from_numpy(h5f['beta'][()]).view(out_planes)
    mean = torch.from_numpy(h5f['mean'][()]).view(out_planes)
    var = torch.from_numpy(h5f['var'][()]).view(out_planes)

    assert state_dict[name_pth + '.conv.weight'].size() == weight.size()
    assert state_dict[name_pth + '.bn.weight'].size() == gamma.size()
    assert state_dict[name_pth + '.bn.bias'].size() == beta.size()
    assert state_dict[name_pth + '.bn.running_mean'].size() == mean.size()
    assert state_dict[name_pth + '.bn.running_var'].size() == var.size()

    state_dict[name_pth + '.conv.weight'] = weight

    # TODO why ones?
    state_dict[name_pth + '.bn.weight'] = gamma
    state_dict[name_pth + '.bn.bias'] = beta
    state_dict[name_pth + '.bn.running_mean'] = mean
    state_dict[name_pth + '.bn.running_var'] = var
    h5f.close()

def load_Mixed(state_dict, modality, dump_dir='./data/dump', name_pth='features.5', name_tf='Mixed_3b'):
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch0.0',
                name_tf=name_tf + '/Branch_0/Conv3d_0a_1x1')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch1.0',
                name_tf=name_tf + '/Branch_1/Conv3d_0a_1x1')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch1.1',
                name_tf=name_tf + '/Branch_1/Conv3d_0b_3x3')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch2.0',
                name_tf=name_tf + '/Branch_2/Conv3d_0a_1x1')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch2.1',
                name_tf=name_tf + '/Branch_2/Conv3d_0b_3x3')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch3.1',
                name_tf=name_tf + '/Branch_3/Conv3d_0b_1x1')


def load_Mixed_5b(state_dict, modality, dump_dir='./data/dump', name_pth='features.14', name_tf='Mixed_5b'):
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch0.0',
                name_tf=name_tf + '/Branch_0/Conv3d_0a_1x1')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch1.0',
                name_tf=name_tf + '/Branch_1/Conv3d_0a_1x1')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch1.1',
                name_tf=name_tf + '/Branch_1/Conv3d_0b_3x3')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch2.0',
                name_tf=name_tf + '/Branch_2/Conv3d_0a_1x1')

    # I think Conv3d_0a_3x3 is author's typo
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch2.1',
                name_tf=name_tf + '/Branch_2/Conv3d_0a_3x3')
    load_conv3d(state_dict, modality, dump_dir, name_pth + '.branch3.1',
                name_tf=name_tf + '/Branch_3/Conv3d_0b_1x1')

def load_Logits(state_dict, modality, dump_dir='./data/dump', name_pth='features.18',
                name_tf='Logits/Conv3d_0c_1x1'):
    h5f = h5py.File(dump_dir + modality + "/" + name_tf + "/" + name_tf.split('/')[-1] + '.h5', 'r')

    weight = torch.from_numpy(h5f['weights'][()]).permute(4, 3, 0, 1, 2)
    bias = torch.from_numpy(h5f['bias'][()])

    assert state_dict[name_pth + '.weight'].size() == weight.size()
    assert state_dict[name_pth + '.bias'].size() == bias.size()

    # weight need (out_channel, in_channel, L, H, W)
    state_dict[name_pth + '.weight'] = weight
    state_dict[name_pth + '.bias'] = bias

    h5f.close()

if __name__ == '__main__':


    parser = argparse.ArgumentParser()
    # Model Parmeters
    parser.add_argument('--dump_dir', type=str, default='../data/dump/',
                        help='source directory')
    parser.add_argument('--target_dir', type=str, default=None,
                        help='source directory')
    parser.add_argument('--modality', type=str, default='rgb_imagenet',
                        help='rgb_scratch , rgb_imagenet, flow_scratch, flow_imagenet')
    
    args = parser.parse_args()
    
    if args.target_dir is None:

        if os.path.exists("../data/pytorch_checkpoints/") == False:
            os.mkdir("../data/pytorch_checkpoints/")

        target_dir = "../data/pytorch_checkpoints/" + args.modality + ".pth"

    else:

        if os.path.exists(args.target_dir) == False:
            os.mkdir(args.target_dir)

        target_dir = args.target_dir


    modality = args.modality
    dump_dir = args.dump_dir

    input_channel = 3 if 'rgb' in modality else 2
    i3d = I3D(input_channel=input_channel)

    state_dict = i3d.state_dict()
    load_conv3d(state_dict, modality, dump_dir, name_pth='features.0', name_tf='Conv3d_1a_7x7')
    load_conv3d(state_dict, modality, dump_dir, name_pth='features.2', name_tf='Conv3d_2b_1x1')
    load_conv3d(state_dict, modality, dump_dir, name_pth='features.3', name_tf='Conv3d_2c_3x3')

    load_Mixed(state_dict, modality, dump_dir, name_pth='features.5', name_tf='Mixed_3b')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.6', name_tf='Mixed_3c')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.8', name_tf='Mixed_4b')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.9', name_tf='Mixed_4c')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.10', name_tf='Mixed_4d')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.11', name_tf='Mixed_4e')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.12', name_tf='Mixed_4f')
    load_Mixed_5b(state_dict, modality, dump_dir, name_pth='features.14', name_tf='Mixed_5b')
    load_Mixed(state_dict, modality, dump_dir, name_pth='features.15', name_tf='Mixed_5c')
    load_Logits(state_dict, modality, dump_dir, name_pth='features.18', name_tf='Logits/Conv3d_0c_1x1')

    i3d.load_state_dict(state_dict)
    torch.save(i3d.state_dict(), target_dir)