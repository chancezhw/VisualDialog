import sys
sys.path.append('../')

import numpy as np
import theano.tensor as T
import theano

from utils import _concat, load_obj
from preprocess import preprocess
from basic_layers import param_init_lstm, lstm_layer
from adam import adam
import minibatch

from collections import OrderedDict
import time

'''
This script trains a sequence to sequence model on language only for better initialization of decoder and encoder LSTMs.
'''
# initializing constants
DATA_DIR = '../../Data/'
MODEL_DIR = '../../Models/'

# encoder lstm
ENCODER_EMBEDDING = 512
lstm_prefix_e = 'lstm_e'

# decoder layer
lstm_prefix_d = 'lstm_d'
MAX_TOKENS = 60

# specify number of epochs to be trained for
EPOCHS = 150

# clip gradients beyond certain magnitude
GRAD_CLIP = 5.0

# other training constants
reduced_instances = -1
learning_rate = 0.001

# getting dimensionality
print "Loading embedding matrix"
try:
	embed = np.transpose(np.load(MODEL_DIR + 'embedding_matrix.npy').astype('float32'))
	embeddings = T.as_tensor_variable(embed)
	load_embedding_data = True
except:
	print "Unable to load embedding matrix\nWill be created after preprocessing"
	load_embedding_data = False

print "Loading dictionaries"
try:
	# loading dictionaries
	word_idx_map = load_obj(MODEL_DIR + 'dictionary.pkl')
	idx_word_map = load_obj(MODEL_DIR + 'reverse_dictionary.pkl')
	load_dict = True
except:
	print "Unable to load dictionaries\nWill be loaded after preprocessing"
	load_dict = False

print "Preprocessing data"
if len(sys.argv) <=1 or int(sys.argv[1]) == 0:
	# preprocess the training data to get input matrices and tensors
	image_features, questions_tensor, answers_tensor, answers_tokens_idx = preprocess(DATA_DIR, 
																		   load_dict=load_dict, 
																		   load_embedding_matrix=load_embedding_data, 
																		   save_data=False,
																		   reduced_instances=reduced_instances)
else:
	image_features, captions, questions, answers_options, correct_options = preprocess(DATA_DIR,
																		 load_dict=True,
																		 load_embedding_matrix=True,
																		 split='Val',
																		 save_data=False,
																		 reduced_instances=1000)
EMBEDDINGS_DIM = embed.shape[0]

if len(sys.argv) <=1 or int(sys.argv[1]) == 0:
	print "Preparing minibatches"
	train_data = minibatch.data(image_features, questions_tensor, answers_tensor, answers_tokens_idx, len(idx_word_map), batch_size=64)

def initialize(address=None):
	'''
	Initialize the parameters for the model
	address: load pre-saved values for weights of this model
	'''
	if address is None:
		params = OrderedDict()
		global EMBEDDINGS_DIM, ENCODER_EMBEDDING, lstm_prefix_e, lstm_prefix_d

		# encoder layer
		params = param_init_lstm(params, _concat(lstm_prefix_e, 1), EMBEDDINGS_DIM, ENCODER_EMBEDDING)
		params = param_init_lstm(params, _concat(lstm_prefix_e, 2), ENCODER_EMBEDDING, ENCODER_EMBEDDING)

		# decoding layer
		params = param_init_lstm(params, _concat(lstm_prefix_d, 1), EMBEDDINGS_DIM, ENCODER_EMBEDDING)
		params = param_init_lstm(params, _concat(lstm_prefix_d, 2), ENCODER_EMBEDDING, EMBEDDINGS_DIM)
	else:
		params = np.load(address)

	tparams = OrderedDict()
	for key, val in params.iteritems():
		print key, ': ', val.shape
		tparams[key] = theano.shared(val, name=key)

	return tparams

def build_encoder(tparams):
	'''
	Builds computation graph for encoder
	'''
	global lstm_prefix_e

	# steps x samples x dimensions
	que = T.tensor3('que', dtype='float32')

	qsteps = que.shape[0]

	# steps x samples
	if len(sys.argv) <=1 or int(sys.argv[1]) == 0:
		qmask = T.matrix('qmask', dtype='float32')
	else:
		# validation does not require masking as it is stochastic
		qmask = None

	# output for the first layer of lstm
	out_1 = lstm_layer(tparams, que, _concat(lstm_prefix_e, 1), mask=qmask, n_steps = qsteps)

	# restructure
	in_2 = T.as_tensor_variable(out_1[0])
	
	out_2 = lstm_layer(tparams, in_2, _concat(lstm_prefix_e, 2), mask=qmask, n_steps=qsteps)

	# samples x dim_projection
	qcode = out_2[0][-1]

	if len(sys.argv) <=1 or int(sys.argv[1]) == 0:
		return que, qmask, qcode
	else:
		return que, qcode

def build_decoder(tparams, code, max_steps):
	'''
	Build computational graph for a generative decoder
	'''

	global embeddings, word_idx_map, lstm_prefix_d

	def _decode_step(sbelow, sbefore_1, sbefore_2, cell_before_1, cell_before_2):
		'''
		Custom step for decoder, where the output of 2nd LSTM layer is fed into the 1st LSTM layer
		'''
		h_1, c_1 = lstm_layer(tparams, sbelow, _concat(lstm_prefix_d, 1), init_state=sbefore_1, init_memory=cell_before_1, one_step=True)

		h_2, c_2 = lstm_layer(tparams, h_1, _concat(lstm_prefix_d, 2), init_state=sbefore_2, init_memory=cell_before_2, one_step=True)

		return h_2, h_1, h_2, c_1, c_2
		
		
	def _softmax(inp):
		'''
		Chooses the right element from the outputs for softmax
		'''
		# for numerical stability of the output, a small value is added to all probabilities
		return T.nnet.softmax(T.dot(inp, embeddings)) + 1e-8

	n_samples = code.shape[0]
	hdim1 = code.shape[1]
	hdim2 = embeddings.shape[0]

	init_h1 = code
	init_h2 = T.alloc(0., n_samples, hdim2)
	# memory_1 = T.alloc(0., n_samples, hdim1)
	memory_1 = code
	memory_2 = T.alloc(0., n_samples, hdim2)

	init_token = T.tile(embeddings.T[word_idx_map['<sos>'], :], (n_samples, 1))
	
	# initial hidden state for both 1st layer is code
	tokens, updates = theano.scan(_decode_step,
									outputs_info=[init_token, init_h1, init_h2, memory_1, memory_2],
									n_steps=max_steps)

	tokens = T.as_tensor_variable(tokens[2])

	soft_tokens, updates = theano.scan(_softmax, sequences=tokens)

	return T.as_tensor_variable(soft_tokens)

# actual graph for seq2seq
if len(sys.argv) > 2:
	tparams = initialize(sys.argv[2])
else:
	tparams = initialize()

# Training
if len(sys.argv) <=1:
	print "Building encoder for the model"
	que, qmask, qcode = build_encoder(tparams)

	qcode_printed = theano.printing.Print('Encoded value: ')(qcode)
	qmask_printed = theano.printing.Print('Mask: ')(qmask)
	# timesteps x number of answers in minibatch x vocabulary size
	ans = T.tensor3('ans', dtype='int8')

	print "Building decoder"
	pred = build_decoder(tparams, qcode, ans.shape[0])

	print "Building cost function"
	# cost function
	cost = (-T.log(pred) * ans).sum()

	inps = [que, qmask, ans]

	print "Constructing graph"
	f_cost = theano.function(inps, [cost, qcode_printed, qmask_printed], on_unused_input='ignore', profile=False)

	print "Computing gradients"
	param_list=[val for key, val in tparams.iteritems()]
	grads = T.grad(cost, wrt=param_list)

	# gradients are clipped beyond certain values
	g2 = 0.
	for g in grads:
		g2 += (g**2).sum()
	new_grads = []
	for g in grads:
		new_grads.append(T.switch(g2 > (GRAD_CLIP**2),
									g / T.sqrt(g2)*GRAD_CLIP, g))
	grads = new_grads

	# learning rate
	lr = T.scalar(name='lr', dtype='float32')

	# gradients, update parameters
	print "Setting up optimizer"
	f_grad_shared, f_update = adam(lr, tparams, grads, inps, cost)

	# set learning rate before training
	lrate = learning_rate

	# time and cost will be output to the text file in BugReports folder
	if len(sys.argv) > 2:
		EPOCH_START = int(sys.argv[2].split('_')[-1].split('.')[0])
		training_output = open('../../BugReports/seq2seq_mask_train_output_' + str(reduced_instances) + '_' + str(learning_rate) + '.txt','a')
	else:
		EPOCH_START = 0
		training_output = open('../../BugReports/seq2seq_mask_train_output_' + str(reduced_instances) + '_' + str(learning_rate) + '.txt','w')

	for epoch in range(EPOCH_START, EPOCHS):
		train_data.reset()

		print 'Epoch: ', epoch + 1
		epoch_cost = 0.0
		epoch_start = time.time()

		for batch_idx in range(train_data.batches):
			t_start = time.time()
			cost = f_grad_shared(*train_data.get_batch_seq2seq())
			f_update(lrate)
			td = time.time() - t_start

			epoch_cost += cost

			# if not batch_idx % 20:
			# 	training_output.write('Epoch: ' + str(epoch) + ', Batch ID: ' + str(batch_idx) + ', Cost: ' + str(cost) + ', Time: ' + str(td) + '\n')

		print 'Epoch:', epoch + 1, 'Cost:', epoch_cost, 'Time: ', time.time()-epoch_start
		training_output.write('Epoch: ' + str(epoch + 1) + ', Cost: ' + str(epoch_cost) + ', Time: ' + str(time.time()-epoch_start) + '\n')

		if (epoch + 1) % 5 == 0:
			print 'Saving... '

			params = {}
			for key, val in tparams.iteritems():
				params[key] = val.get_value()

			# numpy saving
			np.savez(MODEL_DIR + 'Seq2Seq/seq2seq_mask_' + str(reduced_instances) + '_' + str(learning_rate) + '_' + str(epoch + 1)+'.npz', **params)
			np.savez(MODEL_DIR + 'Backup/seq2seq_mask_' + str(reduced_instances) + '_' + str(learning_rate) + '_' + str(epoch + 1)+'.npz', **params)
			# np.save(MODEL_DIR + 'Backup/seq2seq_mask_' + str(reduced_instances) + '_' + str(learning_rate) + '_' + str(epoch + 1)+'.npy', params)
			print 'Done!'

		print 'Completed Epoch ', epoch + 1 
# Validation
else:
	que, qcode = build_encoder(tparams)

	qcode_print = theano.printing.Print('Encoded Value: ')(qcode)

	print "Building decoder"
	pred = build_decoder(tparams, qcode, MAX_TOKENS)

	inps = [que]
	f = theano.function(inps, pred, on_unused_input='ignore', profile=False)

	if len(sys.argv) > 3:
		rank_file = open(sys.argv[3], 'w')

	for idx in range(image_features.shape[0]):
		print "Image: ", idx + 1

		# 10 questions per image
		for i in range(10):
			out = f(questions[idx][i].reshape((questions[idx][i].shape[0], 1, questions[idx][i].shape[1])))
			out = out.reshape((out.shape[0], out.shape[2]))
			out_idx = np.argmax(out, axis=1)
			out = np.transpose(embed)[out_idx]

			ans_end = MAX_TOKENS
			for j in out_idx:
				if j == word_idx_map['<eos>']:
					ans_end = j + 1
					print '<eos>'
					break
				print idx_word_map[j],

			# extract ranking of correct option
			scores = []
			for options_i, option in enumerate(answers_options[idx][i]):
				len_eval = min(len(option), ans_end)
				score = (out[:len_eval, :] * option[: len_eval, :]).sum()/len_eval
				scores.append([score, options_i])
				# print score
			
			scores.sort(key=lambda x: x[0], reverse=True)
			cor = int(correct_options[idx][i])
			
			for r, pair in enumerate(scores):
				if cor == pair[1]:
					rank = r + 1
					break
			
			if len(sys.argv) > 3:
				rank_file.write(str(rank) + ',' + str(scores[rank-1][0]) + '\n')

			print "Correct option's score:", scores[rank-1][0], 'at rank:', rank 