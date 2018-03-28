# Implements the weak supervision task of training a recurrent neural network
# to predict the LDA topic assignments for abstracts

from data_utils import *
import tensorflow as tf
import matplotlib.pyplot as plt
# suppress warnings about CPU
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

class Config:
	"""
	Helper class that stores model hyperparameters and information about dataset.
	RNN objects are passed a Config() object at instantiation, so any call to
	the variables in Config should use self.config.variable_name.
	"""
	num_epochs = 20
	batch_size = 128
	num_classes = 10
	embed_size = 200
	max_length = 200
	hidden_size = 300
	learning_rate = 0.001
	dropout_rate = 0.5

class RNN():
	"""
	Class that abstracts from the TensorFlow computational graph for a RNN learning
	task. Contains methods that build the computational graph and train the RNN.
	"""
	def __init__(self, config, pretrained_embeddings):
		"""
		Basic constructor that initializes class variables.
		"""
		self.config = config
		self.pretrained_embeddings = pretrained_embeddings
		self.add_placeholders()
		self.logits, self.states = self.add_prediction_op()
		self.loss = self.add_loss_op(self.logits)
		self.train_op = self.add_training_op(self.loss)

	def add_placeholders(self):
		"""
		Creates placeholder tensors to store the input vectorized abstracts, their unpadded 
		lengths, ground truth labels, and dropout rate.
		"""
		self.abstracts_placeholder = tf.placeholder(tf.int32, shape=(None, self.config.max_length))
		self.lengths_placeholder = tf.placeholder(tf.int32, shape=(None,))
		self.labels_placeholder = tf.placeholder(tf.int32, shape=(None,))
		self.dropout_placeholder = tf.placeholder(tf.float64)

	def create_feed_dict(self, abstracts_batch, lengths_batch, labels_batch=None, dropout_rate=1):
		"""
		Helper method that creates the feed dictionary that maps from placeholder to input
		values.
		"""
		feed_dict = {}
		feed_dict[self.abstracts_placeholder] = abstracts_batch
		feed_dict[self.lengths_placeholder] = lengths_batch
		if labels_batch is not None: feed_dict[self.labels_placeholder] = labels_batch
		feed_dict[self.dropout_placeholder] = dropout_rate
		return feed_dict
	
	def add_embedding_op(self):
		"""	
		Adds the embedding layer that maps from the vectorized abstracts to word embeddings.
		"""
		embedding_tensor = tf.Variable(self.pretrained_embeddings)
		lookup = tf.nn.embedding_lookup(embedding_tensor, self.abstracts_placeholder)
		return lookup

	def add_prediction_op(self):
		"""
		Adds one layer of LSTM cells that computes a hidden state vector for each full pass of
		an abstract, and uses the hidden state vector to compute softmax logit scores for the
		classification labels (0 to 9). Returns both the logits and the hidden state vectors.
		"""
		x = self.add_embedding_op()
		batch_size = tf.shape(x)[0]
		cell = tf.nn.rnn_cell.BasicLSTMCell(self.config.hidden_size)
		init_state = tf.nn.rnn_cell.LSTMStateTuple(tf.zeros(shape=(batch_size, self.config.hidden_size), dtype=tf.float64),
					  							   tf.zeros(shape=(batch_size, self.config.hidden_size), dtype=tf.float64))

		U = tf.get_variable("U", shape=(self.config.hidden_size, self.config.num_classes), dtype=tf.float64, 
											initializer = tf.contrib.layers.xavier_initializer())
		outputs, states = tf.nn.dynamic_rnn(cell, inputs=x, sequence_length=self.lengths_placeholder, initial_state=init_state, dtype=tf.float64)
		# use the hidden state (corresponding to states[1]) when calculating logits
		states_drop = tf.nn.dropout(states[1], self.dropout_placeholder)
		logits = tf.matmul(states_drop, U)

		return (logits, states[1])

	def add_loss_op(self, logits):
		"""
		Adds the final layer that computes the cross entropy loss, assuming that class
		probabilities are calculated using a softmax function.
		"""
		loss = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(labels=self.labels_placeholder, logits=logits))
		return loss

	def add_training_op(self, loss):
		"""
		Creates the training operation, in the form of an AdamOptimizer object that minimizes
		the cross entropy loss returned by add_loss_op().
		"""
		optimizer = tf.train.AdamOptimizer(learning_rate=self.config.learning_rate)
		return optimizer.minimize(loss)

	def train_on_batch(self, sess, abstracts_batch, lengths_batch, labels_batch):
		"""
		Runs the full computational graph on one batch of abstracts to perform one step
		of parameter updates.
		"""
		# create the feed dictionary for this batch
		feed_dict = self.create_feed_dict(abstracts_batch, lengths_batch, labels_batch, self.config.dropout_rate)
		_, loss = sess.run([self.train_op, self.loss], feed_dict)
		return loss

	def predict_on_batch(self, sess, abstracts_batch, lengths_batch):
		"""
		Makes predictions on one batch of abstracts.
		"""
		# create feed dictionary for this batch
		feed_dict = self.create_feed_dict(abstracts_batch, lengths_batch)
		predictions = sess.run(tf.argmax(self.logits, axis=1), feed_dict)
		return predictions

	def get_states_on_batch(self, sess, abstracts_batch, lengths_batch):
		"""
		Gets the final hidden state vector of the RNN for all input abstracts.
		"""
		feed_dict = self.create_feed_dict(abstracts_batch, lengths_batch)
		states = sess.run(self.states, feed_dict)
		return np.array(states)

def preprocess_data(topics_file, labels_file, abstracts_file, embeddings_file, max_length):
	"""
	Helper function to load and preprocess data for the RNN. Returns the padded, vectorized
	abstracts, along with their unpadded lengths, the LDA labels, and word embeddings.
	"""
	# load LDA topics and abstract labels into memory (as lists)
	topics, labels = load_labels(topics_file, labels_file)
	# load tokenized abstracts and file names into memory (as lists)
	fnames, abstracts = load_abstracts(abstracts_file)
	# load pre-trained embeddings and vocabulary into memory (as arrays)
	vocab, embeddings = load_embeddings_array(embeddings_file)
	# pad abstracts, and add <NULL> token to vocabulary and word embeddings
	new_abstracts, orig_lengths, new_vocab, new_embeddings = pad_abstracts(abstracts, vocab, embeddings, max_length)
	# vectorize abstracts
	vectorized_abstracts = vectorize_abstracts(new_abstracts, new_vocab)
	return(vectorized_abstracts, orig_lengths, labels, new_embeddings)

def split_data(abstracts, lengths, labels, train_ratio=0.99):
	"""
	Shuffles and splits the available data into training and validation sets.
	"""
	indices = np.arange(len(abstracts))
	np.random.shuffle(indices)
	split_index = int(len(indices)*train_ratio)
	# get indices for training and validation sets
	train_indices = np.array(indices[ : split_index])
	val_indices = np.array(indices[split_index : ])
	# slice out training and validation sets, and return
	train_set = (abstracts[train_indices], lengths[train_indices], labels[train_indices])
	val_set =(abstracts[val_indices], lengths[val_indices], labels[val_indices])
	return(train_set, val_set)

def train(abstracts, lengths, labels, embeddings):
	"""
	Main loop that implements the training over all epochs.
	"""
	config = Config()
	rnn = RNN(config, embeddings)
	print("Initialized RNN object.")
	init = tf.global_variables_initializer()
	saver = tf.train.Saver()
	print("===============================================================")
	with tf.Session() as session:
		session.run(init)
		for epoch in range(config.num_epochs):
			print("\nTraining epoch number %i of %i:" % (epoch+1, config.num_epochs))
			prog = Progbar(target=1 + len(labels)/config.batch_size)
			losses = []
			for i, batch in enumerate(get_minibatches(abstracts, lengths, labels, config.batch_size)):
				loss = rnn.train_on_batch(session, *batch)
				losses.append(loss)
				prog.update(i+1, [("Loss", loss)])
				save_path = saver.save(session, "./weights/model2")
			save_loss(losses)
	print("\n\n===============================================================\n")		

def save_loss(losses):
	"""
	Writes the training losses to a text file.
	"""
	with open("training_loss2", "a") as f:
		for loss in losses:
			f.write("%s " % str(loss))
		f.write("\n")

def predict(abstracts, lengths, labels, embeddings, get_states=False):
	"""
	Uses the trained model weights to make a prediction on the validation set.
	If @get_states is set to True, obtains the final hidden state vector of 
	the RNN for all input abstracts, instead of making predictions.
	"""
	tf.reset_default_graph()
	print("Making predictions on validation set...")
	config = Config()
	rnn = RNN(config, embeddings)
	
	if get_states: 
		requested_op = rnn.get_states_on_batch
	else:
		requested_op = rnn.predict_on_batch
	saver = tf.train.Saver()
	
	with tf.Session() as session:
		saver.restore(session, "./weights/model1")
		out = requested_op(session, abstracts, lengths)
	
	if get_states:
		return out
	else:
		accuracy = np.mean(out == labels)
		return accuracy

def get_all_states(abstracts, lengths, labels, embeddings):
	"""
	Uses the trained model weights to obtain the final hidden state vector
	of the RNN for all abstracts. Differs from the predict() function in the
	use of a generator here to prevent out-of-memory issues.
	"""
	tf.reset_default_graph()
	print("Getting hidden state for all abstracts...")
	config = Config()
	rnn = RNN(config, embeddings)
	saver = tf.train.Saver()
	states = np.empty(shape=(0, config.hidden_size), dtype=float)

	with tf.Session() as session:
		saver.restore(session, "./weights/model1")
		prog = Progbar(target=1 + len(labels)/config.batch_size)
		for i, batch in enumerate(get_minibatches(abstracts, lengths, labels, config.batch_size, shuffle=False)):
			batch_states = rnn.get_states_on_batch(session, batch[0], batch[1])
			states = np.append(states, batch_states, axis=0)
			prog.update(i+1)
	print("\n")
	return states

def save_states(states):
	"""
	Writes the final hidden state vector of the RNN for all input abstracts
	into a text file.
	"""
	np.savetxt("hidden_states", states, delimiter=" ")

if __name__ == "__main__":
	start = time.time()
	# get command line arguments
	parser = argparse.ArgumentParser()
	parser.add_argument("--lda-topics", type=str, default="lda_topics_final", help="lda_topics file")
	parser.add_argument("--lda-assignments", type=str, default="lda_assignments_final", help="lda_assignments file")
	parser.add_argument("--abs-dir-tok", type=str, default="data/abstracts_tokenized", help="Directory that stores tokenized abstracts.")
	parser.add_argument("--embeddings", type=str, default="glove/embeddings.txt", help="Path to pre-trained word embeddings.")
	parser.add_argument("--max-length", type=int, default=200, help="Maximum abstract length.")
	args = parser.parse_args()	

	abstracts, lengths, labels, embeddings = preprocess_data(args.lda_topics, args.lda_assignments, args.abs_dir_tok, args.embeddings, args.max_length)
	train_set, validation_set = split_data(abstracts, lengths, labels)
	# train(*train_set, embeddings)
	# states = predict(*validation_set, embeddings, get_states=True)
	states = get_all_states(abstracts, lengths, labels, embeddings)
	save_states(states)
	print("Total time taken: %.2f" % (time.time()-start))