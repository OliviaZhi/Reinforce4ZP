#coding=utf8
import os
import sys
import re
import math
import timeit
import cPickle
import copy
import time
sys.setrecursionlimit(1000000)
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.autograd as autograd
from torch.optim import lr_scheduler
from conf import *
from data_generater import *
from net import *

random.seed(0)
numpy.random.seed(0)
torch.manual_seed(args.random_seed)
torch.cuda.manual_seed(args.random_seed)
print "PID", os.getpid()
torch.cuda.set_device(args.gpu)


def main():
    # reinforcement learning
    if os.path.isfile("./data/train_data"):
        read_f = file("./data/train_data","rb")
        train_generater = cPickle.load(read_f)
        read_f.close()
    else:
        train_generater = DataGnerater("train",nnargs["batch_size"])
        train_generater.devide()
    test_generater = DataGnerater("test",256)

    read_f = file("./data/emb","rb")
    embedding_matrix,_,_ = cPickle.load(read_f)
    read_f.close()

    model = Network(nnargs["embedding_size"],nnargs["embedding_dimention"],embedding_matrix,nnargs["hidden_dimention"],2).cuda()
    model_ = torch.load("./models/model")
    mcp = list(model.parameters())
    mp = list(model_.parameters())
    n = len(mcp)
    for i in range(0, n): 
        mcp[i].data[:] = mp[i].data[:]
    optimizer = optim.Adagrad(model.parameters(),lr=0.000009)
    best = {"sum":0.0}
    best_model = Network(nnargs["embedding_size"],nnargs["embedding_dimention"],embedding_matrix,nnargs["hidden_dimention"],2).cuda()
    re = evaluate_test(test_generater,model)
    print "Performance on Test Before RL: F",re["f"]

    prec_list = []
    rec_list = []
    f1_list = []
    for echo in range(50):
        info = "["+echo*">"+" "*(50-echo)+"]"
        sys.stderr.write(info+"\r")

        # chg 
        value_list = []
        log_prob_list = []
        rewards_list = []
        entropy_list = []
        numofdata = 0
        for data in train_generater.generate_data(shuffle=True):
            numofdata += 1
            zp_rein = torch.tensor(data["zp_rein"]).type(torch.cuda.LongTensor)
            zp_pre = torch.tensor(data["zp_pre"]).type(torch.cuda.LongTensor)
            zp_pre_mask = torch.tensor(data["zp_pre_mask"]).type(torch.cuda.FloatTensor)
            zp_post = torch.tensor(data["zp_post"]).type(torch.cuda.LongTensor)
            zp_post_mask = torch.tensor(data["zp_post_mask"]).type(torch.cuda.FloatTensor)
            candi_rein = torch.tensor(data["candi_rein"]).type(torch.cuda.LongTensor)
            candi = torch.tensor(data["candi"]).type(torch.cuda.LongTensor)
            candi_mask = torch.tensor(data["candi_mask"]).type(torch.cuda.FloatTensor)
            feature = torch.tensor(data["fl"]).type(torch.cuda.FloatTensor)
            zp_pre = torch.transpose(zp_pre,0,1)
            mask_zp_pre = torch.transpose(zp_pre_mask,0,1)
            hidden_zp_pre = model.initHidden()
            for i in range(len(mask_zp_pre)):
                hidden_zp_pre = model.forward_zp_pre(zp_pre[i],hidden_zp_pre,dropout=nnargs["dropout"])*torch.transpose(mask_zp_pre[i:i+1],0,1)
            zp_pre_rep = hidden_zp_pre[zp_rein]
            zp_post = torch.transpose(zp_post,0,1)
            mask_zp_post = torch.transpose(zp_post_mask,0,1)
            hidden_zp_post = model.initHidden()
            for i in range(len(mask_zp_post)):
                hidden_zp_post = model.forward_zp_post(zp_post[i],hidden_zp_post,dropout=nnargs["dropout"])*torch.transpose(mask_zp_post[i:i+1],0,1)
            zp_post_rep = hidden_zp_post[zp_rein]
            candi = torch.transpose(candi,0,1)
            mask_candi = torch.transpose(candi_mask,0,1)
            hidden_candi = model.initHidden()
            for i in range(len(mask_candi)):
                hidden_candi = model.forward_np(candi[i],hidden_candi,dropout=nnargs["dropout"])*torch.transpose(mask_candi[i:i+1],0,1)
            candi_rep = hidden_candi[candi_rein]
            output,output_softmax = model.generate_score(zp_pre_rep,zp_post_rep,candi_rep,feature,dropout=nnargs["dropout"])
            target = autograd.Variable(torch.from_numpy(data["result"]).type(torch.cuda.LongTensor))

            # get history???
            nps = torch.zeros(len(candi_rep),len(candi_rep)).type(torch.cuda.FloatTensor)
            for s,e in data["s2e"]:
                if s == e:continue
                thre = output_softmax[s:e][:,1].data.cpu().numpy()
                lu = numpy.clip(numpy.floor(numpy.random.rand(len(thre)) / thre), 1, 0).astype(int)
                heihei = torch.from_numpy(lu).type(torch.cuda.FloatTensor)
                for i in range(1,len(lu)):
                    nps[s+i][s:s+i] = heihei[:i]
            nps = autograd.Variable(nps)
            history = nps.view(len(candi_rep),len(candi_rep),1)*candi_rep
            maxh,_ = torch.max(history,1)
            ave = torch.sum(history,1)/(torch.sum(nps.view(len(candi_rep),len(candi_rep),1),1)+1e-10)
            history = torch.cat([maxh,ave],1)
            # chg   
            action_values,probs,state_values = model.generate_scores(zp_pre_rep,zp_post_rep,candi_rep,history,feature,dropout=nnargs["dropout"])
            value_list.append(state_values)

            lu = numpy.zeros(len(state_values),dtype='int32')
            probs_numpy = probs.data.cpu().numpy()
            for i in range(len(lu)):
                if numpy.random.rand(1) < 0.01:
                    lu[i] = numpy.random.choice([0,1],1,p=probs_numpy[i])
                else:
                    lu[i] = probs_numpy[i].argmax()
            #thre = probs[:,1].data.cpu().numpy()
            #lu = numpy.clip(numpy.floor(numpy.random.rand(len(thre)) / thre), 1, 0).astype(int)
            gold = data["target"]
#           if float(sum(gold)) == 0 or sum(gold*lu) == 0 or sum(lu) == 0:continue
#            prec = -float(sum(gold*lu))/float(numpy.count_nonzero(lu))
#            rec = -float(sum(gold*lu))/float(numpy.count_nonzero(gold))
#           sc = 0 if (rec == 0.0 or prec == 0.0) else 2.0/(1.0/prec+1.0/rec)
#            if sc == 0:continue

            rewards = numpy.full((len(lu),1),0.0)
            pl = lu.tolist()
            for i in range(len(pl)):
                if lu[i]==1 and gold[i]==-1:
                    rewards[i] += 20.0
                if lu[i]==1 and gold[i]==0:
                    rewards[i] -= 20.0
                if lu[i]==0 and gold[i]==-1:
                    rewards[i] -= 6.0
                if lu[i]==0 and gold[i]==0:
                    rewards[i] += 2.0

#            rewards = torch.tensor(-1.0*rewards).type(torch.cuda.FloatTensor)
            rewards = -1.0*rewards

#            print(rewards.shape)
            
            accRewards = []
            R = 0
            for r in rewards[::-1]:
                R = r + 0.98*R
                accRewards.insert(0,R)
            accRewards = torch.tensor(accRewards).type(torch.cuda.FloatTensor)

            log_probs = probs.log()
#	    print(log_probs)
#	    print(log_probs.shape) 
            actions = torch.cuda.LongTensor(lu).view(-1,1)
#	    print(actions)
#	    print(actions.shape)
            chosen_action_log_probs = log_probs.gather(1,actions)
            advantages = accRewards - state_values

            entropies = -(log_probs * probs).sum(1)
            entropy_list.append(entropies)
            action_gain = chosen_action_log_probs*advantages
            actor_loss = (-action_gain + 0.01*entropies).sum()
            critic_loss = advantages.pow(2).sum()
            
            optimizer.zero_grad()
            loss = critic_loss + actor_loss
            loss.backward()
            optimizer.step()
        
        re = evaluate(train_generater,model)
        if re >= best["sum"]:
            mcp = list(best_model.parameters())
            mp = list(model.parameters())
            for i in range(0, len(mcp)): 
                mcp[i].data[:] = mp[i].data[:]
            best["sum"] = re

        temp = evaluate_test(test_generater, model)
        print(temp)
        prec_list.append(temp["p"])
        rec_list.append(temp["r"])
        f1_list.append(temp["f"])


    print >> sys.stderr
    re = evaluate_test(test_generater,best_model)
    print "Performance on Test Final:",re
    torch.save(best_model, "./models/model.final")
    print "Dev",best["sum"]

    with open("prec_vs_50epoch_rwd202062_lr98.txt", "w") as output:
        output.write(str(prec_list))
    with open("rec_vs_50epoch_rwd202062_lr98.txt", "w") as output:
        output.write(str(rec_list))
    with open("f1_vs_50epoch_rwd202062_lr98.txt", "w") as output:
        output.write(str(f1_list))


def evaluate(generater,model):
    pr = []
    for data in generater.generate_dev_data():
        zp_rein = torch.tensor(data["zp_rein"]).type(torch.cuda.LongTensor)
        zp_pre = torch.tensor(data["zp_pre"]).type(torch.cuda.LongTensor)
        zp_pre_mask = torch.tensor(data["zp_pre_mask"]).type(torch.cuda.FloatTensor)
        zp_post = torch.tensor(data["zp_post"]).type(torch.cuda.LongTensor)
        zp_post_mask = torch.tensor(data["zp_post_mask"]).type(torch.cuda.FloatTensor)
        candi_rein = torch.tensor(data["candi_rein"]).type(torch.cuda.LongTensor)
        candi = torch.tensor(data["candi"]).type(torch.cuda.LongTensor)
        candi_mask = torch.tensor(data["candi_mask"]).type(torch.cuda.FloatTensor)
        feature = torch.tensor(data["fl"]).type(torch.cuda.FloatTensor)
        zp_pre = torch.transpose(zp_pre,0,1)
        mask_zp_pre = torch.transpose(zp_pre_mask,0,1)
        hidden_zp_pre = model.initHidden()
        for i in range(len(mask_zp_pre)):
            hidden_zp_pre = model.forward_zp_pre(zp_pre[i],hidden_zp_pre)*torch.transpose(mask_zp_pre[i:i+1],0,1)
        zp_pre_rep = hidden_zp_pre[zp_rein]
        zp_post = torch.transpose(zp_post,0,1)
        mask_zp_post = torch.transpose(zp_post_mask,0,1)
        hidden_zp_post = model.initHidden()
        for i in range(len(mask_zp_post)):
            hidden_zp_post = model.forward_zp_post(zp_post[i],hidden_zp_post)*torch.transpose(mask_zp_post[i:i+1],0,1)
        zp_post_rep = hidden_zp_post[zp_rein]
        candi = torch.transpose(candi,0,1)
        mask_candi = torch.transpose(candi_mask,0,1)
        hidden_candi = model.initHidden()
        for i in range(len(mask_candi)):
            hidden_candi = model.forward_np(candi[i],hidden_candi)*torch.transpose(mask_candi[i:i+1],0,1)
        candi_rep = hidden_candi[candi_rein]
        output,output_softmax = model.generate_score(zp_pre_rep,zp_post_rep,candi_rep,feature)
        nps = torch.zeros(len(candi_rep),len(candi_rep)).type(torch.cuda.FloatTensor)
        for s,e in data["s2e"]:
            if s == e:
                continue
            thre = output_softmax[s:e][:,1].data.cpu().numpy()
            lu = numpy.clip(numpy.floor(0.5 / thre), 1, 0).astype(int)
            heihei = torch.tensor(lu).type(torch.cuda.FloatTensor)
            for i in range(1,len(lu)):
                nps[s+i][s:s+i] = heihei[:i]
        history = nps.view(len(candi_rep),len(candi_rep),1)*candi_rep
        maxh,_ = torch.max(history,1)
        ave = torch.sum(history,1)/(torch.sum(nps.view(len(candi_rep),len(candi_rep),1),1)+1e-10)
        history = torch.cat([maxh,ave],1)
        output,output_softmax,_ = model.generate_scores(zp_pre_rep,zp_post_rep,candi_rep,history,feature)
        output_softmax = output_softmax.data.cpu().numpy()
        for s,e in data["s2e"]:
            if s == e:
                continue
            pr.append((data["result"][s:e],output_softmax[s:e]))
    predict = []
    for result,output in pr:
        index = -1
        pro = 0.0
        for i in range(len(output)):
            if output[i][1] > pro:
                index = i
                pro = output[i][1]
        predict.append(result[index])
    return sum(predict)/float(len(predict))

def evaluate_test(generater,model):
    pr = []
    for data in generater.generate_data():
        zp_rein = torch.tensor(data["zp_rein"]).type(torch.cuda.LongTensor)
        zp_pre = torch.tensor(data["zp_pre"]).type(torch.cuda.LongTensor)
        zp_pre_mask = torch.tensor(data["zp_pre_mask"]).type(torch.cuda.FloatTensor)
        zp_post = torch.tensor(data["zp_post"]).type(torch.cuda.LongTensor)
        zp_post_mask = torch.tensor(data["zp_post_mask"]).type(torch.cuda.FloatTensor)
        candi_rein = torch.tensor(data["candi_rein"]).type(torch.cuda.LongTensor)
        candi = torch.tensor(data["candi"]).type(torch.cuda.LongTensor)
        candi_mask = torch.tensor(data["candi_mask"]).type(torch.cuda.FloatTensor)
        feature = torch.tensor(data["fl"]).type(torch.cuda.FloatTensor)
        zp_pre = torch.transpose(zp_pre,0,1)
        mask_zp_pre = torch.transpose(zp_pre_mask,0,1)
        hidden_zp_pre = model.initHidden()
        for i in range(len(mask_zp_pre)):
            hidden_zp_pre = model.forward_zp_pre(zp_pre[i],hidden_zp_pre)*torch.transpose(mask_zp_pre[i:i+1],0,1)
        zp_pre_rep = hidden_zp_pre[zp_rein]
        zp_post = torch.transpose(zp_post,0,1)
        mask_zp_post = torch.transpose(zp_post_mask,0,1)
        hidden_zp_post = model.initHidden()
        for i in range(len(mask_zp_post)):
            hidden_zp_post = model.forward_zp_post(zp_post[i],hidden_zp_post)*torch.transpose(mask_zp_post[i:i+1],0,1)
        zp_post_rep = hidden_zp_post[zp_rein]
        candi = torch.transpose(candi,0,1)
        mask_candi = torch.transpose(candi_mask,0,1)
        hidden_candi = model.initHidden()
        for i in range(len(mask_candi)):
            hidden_candi = model.forward_np(candi[i],hidden_candi)*torch.transpose(mask_candi[i:i+1],0,1)
        candi_rep = hidden_candi[candi_rein]
        output,output_softmax = model.generate_score(zp_pre_rep,zp_post_rep,candi_rep,feature)
        nps = torch.zeros(len(candi_rep),len(candi_rep)).type(torch.cuda.FloatTensor)
        for s,e in data["s2e"]:
            if s == e:
                continue
            thre = output_softmax[s:e][:,1].data.cpu().numpy()
            lu = numpy.clip(numpy.floor(0.5 / thre), 1, 0).astype(int)
            heihei = torch.tensor(lu).type(torch.cuda.FloatTensor)
            for i in range(1,len(lu)):
                nps[s+i][s:s+i] = heihei[:i]
        history = nps.view(len(candi_rep),len(candi_rep),1)*candi_rep
        maxh,_ = torch.max(history,1)
        ave = torch.sum(history,1)/(torch.sum(nps.view(len(candi_rep),len(candi_rep),1),1)+1e-10)
        history = torch.cat([maxh,ave],1)
        output,output_softmax,_ = model.generate_scores(zp_pre_rep,zp_post_rep,candi_rep,history,feature)
        output_softmax = output_softmax.data.cpu().numpy()
        for s,e in data["s2e"]:
            if s == e:
                continue
            pr.append((data["result"][s:e],output_softmax[s:e]))
    predict = []
    for result,output in pr:
        index = -1
        pro = 0.0
        for i in range(len(output)):
            if output[i][1] > pro:
                index = i
                pro = output[i][1]
        predict.append(result[index])
    p = sum(predict)/float(len(predict))
    r = sum(predict)/1713.0
    f = 0.0 if (p == 0 or r == 0) else (2.0/(1.0/p+1.0/r))
    re = {"p":p,"r":r,"f":f}
    return re

if __name__ == "__main__":
    start_time = time.time()
    main()
    print('training time {} seconds'.format(time.time()-start_time))

