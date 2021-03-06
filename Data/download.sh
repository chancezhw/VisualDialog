#!/bin/bash
# sets up the data folder and downloads the appropriate datasets into respective folders

# train
mkdir Training/
cd Training/
wget "http://computing.ece.vt.edu/~abhshkdz/data/visdial/visdial_0.5_train.json"
wget "https://computing.ece.vt.edu/~abhshkdz/data/visdial/visdial_0.9_train.zip"
unzip visdial_0.9_train.zip
rm visdial_0.9_train.zip

# validation
mkdir ../Validation/
cd ../Validation/
wget "http://computing.ece.vt.edu/~abhshkdz/data/visdial/visdial_0.5_val.json"
wget "https://computing.ece.vt.edu/~abhshkdz/data/visdial/visdial_0.9_val.zip"
unzip visdial_0.9_val.zip
rm visdial_0.9_val.zip

# test
mkdir ../Test/
cd ../Test/
wget "http://computing.ece.vt.edu/~abhshkdz/data/visdial/visdial_0.5_test.json"

# ms coco features extracted using the VGG16 architecture
cd ../
wget "http://cs.stanford.edu/people/karpathy/deepimagesent/coco.zip"
unzip coco.zip -d .
cp ./coco/vgg_feats.mat .
rm -rf ./coco/
rm -rf coco.zip

# optionally download the embeddings : Uncomment './download.sh'
# check download script in embedding folder for more details
cd Embeddings
chmod +x ./download.sh
./download.sh