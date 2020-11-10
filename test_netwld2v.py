import numpy as np
import warnings
warnings.filterwarnings("ignore")
import igraph as ig
import argparse
import sys,os
import time
from netwld2v.Netwld2v import Netwld2v
from netpro2vec import utils
import tqdm
import csv
import pandas as pd

# import sklearn library
from sklearn.feature_selection import RFECV
from sklearn.model_selection import StratifiedKFold,RepeatedStratifiedKFold,cross_validate
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import confusion_matrix
from sklearn.svm import SVC

parser = argparse.ArgumentParser(description='Tesing Netpro2vec')
parser.add_argument('-i', "--inputpath", metavar='<inputpath>', type=str, help='input directory (default .)', required=True)
parser.add_argument('-l', "--labelfile", metavar='<labelfile>', type=str, help='label file (path))', required=True)
#parser.add_argument('-n', "--distributions", metavar='<distributions>', nargs='*',  type=str, default=['tm1'], help='list of distribution types (default: %(default)s)') 
parser.add_argument('-n', "--distributions", metavar='<distributions>', type=str, default='tm1', help='distribution type (default: %(default))') 
parser.add_argument('-A', "--vertexattribute", metavar='<vertex-attribute>', type=str, help='vertex attribute', required=False)
parser.add_argument('-X', "--select", help="enable feature elimination (default disabled)", action='store_true')
parser.add_argument('-V', "--validate", help="enable cross-validation (default disabled)", action='store_true')
parser.add_argument('-v', "--verbose", help="enable verobose printing (default disabled)", action='store_true')
parser.add_argument('-o', "--outfile", metavar='<document-filename>', type=str, help='document output file (default None))', default=None, required=False)
parser.add_argument('-L', "--loadfile", metavar='<embed-filename>', type=str, help='loading embedding file (default None))', required=False)
parser.add_argument('-S', "--savefile", metavar='<embed-filename>', type=str, help='saving embedding  file (default None))', required=False)
parser.add_argument('-p', "--label-position", dest='label_position', metavar='<label-position>', type=int, help='label position (default 2)', default=2, required=False)
parser.add_argument('-d', "--dimensions", metavar='<dimensions>', type=int, help='feature dimension (default 512)', default=512, required=False)
parser.add_argument('-w', "--workers", metavar='<workers>', type=int, help='number of workers (default 4)', default=4, required=False)
parser.add_argument('-W', "--recursions", metavar='<recursions>', type=int, help='number of recursions (default 2)', default=2, required=False)
parser.add_argument('-x', "--extension", metavar="<extension>", type=str, default='graphml',choices=['graphml', 'edgelist'], help="file format (graphml, edgelist)) ", required=False)
parser.add_argument('-R', "--seed", metavar="<seed>", type=int, default=42, help="random seed", required=False)


def load_graphs(input_path, dataname, labels, fmt='graphml',verbose=False):
    _tqdm = tqdm.tqdm
    if not verbose: _tqdm = utils.nop
    if os.path.isdir(input_path):
        filenames = os.listdir(input_path)
        utils.vprint("Loading " + dataname + " graphs with igraph...", verbose=verbose)
        graph_list = []
        targets = []
        for f in _tqdm(filenames):
            graph_list.append(ig.load(os.path.join(input_path, f),format=fmt))
            targets += [labels[f.split('.')[0]]]
        y = np.array(targets)
        return graph_list,y
    else:
        raise Exception("Problem opening input dir!")

def main(args):
      tm = time.time()
      # parse arguments
      args = parser.parse_args()
      if not os.path.isdir(args.inputpath):
        raise Exception("--inputpath must be a valid directory")
      if not os.path.isfile(args.labelfile):    
        raise Exception("--labelfile must be a valid label file")
      dataname = args.inputpath.split("/")[-2]
      if not args.loadfile:    # compute embeddings
        # read class labels
        labels= {}
        labelfile = open(args.labelfile)
        for row in list(csv.reader(labelfile, delimiter='\t')):
            labels[row[0]] = row[args.label_position]
        tm0 = time.time()
        graphs,y = load_graphs(args.inputpath, dataname, labels,
                               fmt=args.extension, verbose=args.verbose)
        tm1 = time.time()
        if args.verbose: print("Embeddings...")
        tm2 = time.time()
        print(args.distributions)
        model = Netwld2v(dimensions=args.dimensions,wl_iterations=args.recursions, 
                           annotation=args.distributions,
                           verbose=args.verbose,
                           vertex_attribute=args.vertexattribute,
                           seed=args.seed,
                           workers=args.workers,
                           outdoc=args.outfile)
        model.fit(graphs)
        X = model.get_embedding()
        tm3 = time.time()
        if args.verbose: print("No. of features: " + str(X.shape[1])) 
        tm4 = time.time()
        X = X.astype(np.float)
        scaler = MinMaxScaler(feature_range=(0.0, 1.0))
        X = scaler.fit_transform(X).astype(np.float)
        tm5 = time.time()
        if args.savefile:
           if args.verbose: print("Saving embedding " + args.savefile)
           data = pd.DataFrame(data=np.c_[X,y])
           data.to_csv(args.savefile, index=False)
      else:
        tm0 = time.time()
        if args.verbose: print("Loading embedding " + args.loadfile)
        embedding_data = pd.read_csv(args.loadfile)
        X = embedding_data.iloc[:, :-1]
        X = np.array(X)
        y = np.array(embedding_data.iloc[:, -1])
        tm1 = tm2 = tm3 = tm4 = time.time()
        X = X.astype(np.float)
        scaler = MinMaxScaler(feature_range=(0.0, 1.0))
        X = scaler.fit_transform(X).astype(np.float)
        tm5 = time.time()
        if args.verbose: print("No. of features: " + str(X.shape[1]))
      tm6 = time.time()
      if args.select:
          clf = SVC(kernel="linear")
          sfm = RFECV(estimator=clf, step=10, min_features_to_select=50,
                      cv=StratifiedKFold(random_state=args.seed,n_splits=5),
                      scoring='accuracy')
          sfm = sfm.fit(X, y)
          X = sfm.transform(X)
          if args.verbose: print("Reduced dataset " + str(X.shape[1]))
      tm7 = time.time()
      if args.validate:
          clf = SVC(kernel='linear')
          scoring = ['accuracy', 'precision_macro', "recall_macro", "f1_macro"]
          scores_cv = cross_validate(clf, X, y, scoring=scoring, cv=RepeatedStratifiedKFold(n_splits=10 , n_repeats=10, random_state=args.seed), return_train_score=False)
          print('Acc Avg+Std:\t', (scores_cv['test_accuracy'] * 100).mean(), (scores_cv['test_accuracy'] * 100).std())
          print('Prec Avg+Std:\t', (scores_cv['test_precision_macro'] * 100).mean(),(scores_cv['test_precision_macro'] * 100).std())
          print('Recall Avg+Std:\t', (scores_cv['test_recall_macro'] * 100).mean(), (scores_cv['test_recall_macro'] * 100).std())
          print('F1 Avg+Std:\t', (scores_cv['test_f1_macro'] * 100).mean(), (scores_cv['test_f1_macro'] * 100).std())
      tm8 = time.time()
      print('Time Load: %.2f Embed: %.2f Scaling: %.2f Elim: %.2f Validate: %.2f Tot: %.2f '%(tm1-tm0, tm3-tm2, tm5-tm4,tm7-tm6, tm8-tm7,tm8-tm))

if __name__ == "__main__":
    main(sys.argv[1:])
