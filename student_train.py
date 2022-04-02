import torch
import torch.nn as nn
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler

import os
import copy
from colorama import Fore
from tqdm import tqdm
from time import time

from data import loaders, dataset_sizes
from loss import loss_fn_kd

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')


def train_kd(student:nn.Module, best_student:nn.Module, best_acc:float, 
          criterion=loss_fn_kd, optimizer= ..., scheduler= ..., 
          teacher:nn.Module= ..., epochs:int= 12, path_save_weight:str= ...):
    since = time()
    
    for epoch in range(epochs):
        for phase in ['train', 'val']:
            if phase == 'train': student.train()
            else:                student.eval()

            running_loss = 0.0
            running_corrects = 0.0

            for datas, targets in tqdm(loaders[phase], ncols=64):
                datas, targets = datas.to(device), targets.to(device)

                optimizer.zero_grad()

                with torch.set_grad_enabled(phase == 'train'):
                    outp_Student = student(datas)
                    outp_Teacher = teacher(datas)
                    
                    loss = criterion(outp_Student, targets, outp_Teacher, 
                                     T = 6, alpha = 0.1)
                    _, pred = torch.max(outp_Student, 1)
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item()*datas.size(0)
                running_corrects += torch.sum(pred == targets.data)

            if phase == 'train':
                acc = 100. * running_corrects.double() / dataset_sizes[phase]
                scheduler.step(acc)

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]

            if phase == 'train':
                print(Fore.RED, '\n', 'Epoch: {}/{}'.format(
                    epoch+1, epochs), Fore.RESET, '='*38)
            print('{} - loss = {:.6f}, accuracy = {:.3f}'.format(
                phase, epoch_loss, 100*epoch_acc))

            if phase == 'val':
                print('Time: {}m {:.3f}s'.format(
                    int((time() - since)//60), (time() - since) % 60))
                
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_student = copy.deepcopy(student.state_dict())
                torch.save(student.state_dict(), path_save_weight)
        
    return best_student, best_acc


def training_kd(student:nn.Module, teacher:nn.Module, 
                epochs_freeze:int = 8, epochs_unfreeze:int = 12, 
                path_save_weight:str=None):
    
    if path_save_weight is None:
        if os.path.isdir('Weights'):
            os.makedirs('Weights')
        path_save_weight = os.path.join(
            'Weights', student.__class__.__name__ + '.pth')
    print('Training a model {} using {}'.format(
        student.__class__.__name__, device))

    student.to(device); teacher.to(device).eval()
    criterion = loss_fn_kd
    optimizer = optim.Adam(list(student.children())[-1].parameters(), lr=0.001, 
                           betas=(0.9, 0.999), eps=1e-08, weight_decay=1e-5)
    scheduler = lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.2, 
                                               patience=3, verbose=True)
    
    since = time()
    best_student = copy.deepcopy(student.state_dict())
    best_acc = 0.0
    
    best_student, best_acc = train_kd(student, best_student, best_acc, 
                                   criterion, optimizer, scheduler, 
                                   teacher, epochs_freeze, path_save_weight)
    
    student.load_state_dict(best_student)
    
    time_elapsed = time() - since
    print('CLASSIFIER TRAINING TIME {} : {:.3f}'.format(
        time_elapsed//60, time_elapsed % 60))
    print(Fore.RED, '\n', f'Unfreeze all layers of {student.__class__.__name__}',
          '\n', '=='*22, Fore.RESET, '\n')

    # unfrezz all layer
    for param in student.parameters():
        param.requires_grad = True

    optimizer = optim.Adam(student.parameters(), lr=0.0001, 
                           betas=(0.9, 0.999), eps=1e-08, weight_decay=0)
    scheduler = lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.2, 
                                               patience=2, verbose=True)
    
    best_student, best_acc = train_kd(student, best_student, best_acc, 
                                   criterion, optimizer, scheduler, 
                                   teacher, epochs_unfreeze, path_save_weight)
    
    torch.save(best_student.state_dict(), path_save_weight)
    
    time_elapsed = time() - since
    print('ALL NET TRAINING TIME {} m {:.3f}s'.format(
        time_elapsed//60, time_elapsed % 60))

    return best_student
