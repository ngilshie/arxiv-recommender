# Implements the weak supervision task of training a recurrent neural network
# to predict the LDA topic assignments for abstracts

import numpy as np
from pprint import pprint
import argparse

def load_labels(topics_file, assignments_file):
	"""
	Reads the lda_topics and lda_assignments files generated by lda.py.
	Returns the ground truth labels for each abstract, along with the topics
	"""
	# read in LDA topics
	topics = []
	with open(topics_file) as f:
		for line in f.read().split("\n"):
			topics.append(line)
	# remove last element which is empty
	topics.pop()	
	# read in assignments
	labels = np.genfromtxt(assignments_file, dtype=int, delimiter="\n")
	return (topics, labels)

if __name__ == "__main__":

	# get command line arguments
	parser = argparse.ArgumentParser()
	parser.add_argument("--lda-topics", type=str, default="lda_topics_final", help="lda_topics file")
	parser.add_argument("--lda-assignments", type=str, default="lda_assignments_final", help="lda_assignments file")
	args = parser.parse_args()	

	topics, labels = load_labels(args.lda_topics, args.lda_assignments)

	print(labels)