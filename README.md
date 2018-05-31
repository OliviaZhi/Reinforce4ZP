# Deep Reinforcement Learning for Chinese Zero Pronoun Resolution
Deep neural network models for Chinese zero pronoun resolution learn semantic information for zero pronoun and candidate antecedents, but tend to be short-sighted---they often make local decisions. Ideally, modeling useful information of preceding potential antecedents is critical when later predicting zero pronoun-candidate antecedent pairs. In this paper, we show how to integrate local and global decision-making by exploiting deep reinforcement learning models. Experimental results on OntoNotes 5.0 show that our technique surpasses the state-of-the-art models.


## Requirements
* Python 2.7
   * pytorch(0.4.0)
   * CUDA

## Training Instructions
* Experiment configurations could be found in `conf.py`
* Run `./setup.sh` # it builds the data for training and testing from Ontonotes data.
    * It unzip from `./data/zp_raw_data.zip` and stored in `./data/zp_data`
    * It devides the training dataset into the training and develpment set. The dataset is stored as `train_data` 
* Run `./start.sh` # train the model and get results.
    *   It takes about 25min for pre-training
    *   about 60min for reinforcement learning training on GeForce GTX 1080 Ti
