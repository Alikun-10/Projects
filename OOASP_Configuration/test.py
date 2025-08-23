import sys
import shutil
from subprocess import run, PIPE, TimeoutExpired
import os
import tempfile
import json
import time
import argparse

def call_clingo(clingo, input_names, timeout):
    cmd = [clingo, "--warn=no-atom-undefined", "--warn=no-file-included", "--warn=no-operation-undefined", "--warn=no-global-variable", "--outf=2"] + input_names
    # cmd += ["-t4"] ## solving with 4 threads
    start = time.time()
    output = run(cmd, stdout=PIPE, stderr=PIPE, timeout=timeout)
    end = time.time()
    if output.stderr:
        raise RuntimeError(f"ERROR: {output.stderr}")
    return output.stdout, end-start

def get_solutions(args, output):
    solutions = []
    if not output['Result'].startswith('UNSAT'):
        witnesses = output['Call'][len(output['Call'])-1]['Witnesses']
        if args.optimize:
            cost = output["Models"]["Costs"][0]
            solutions = {tuple(sorted(w['Value'])) for w in witnesses if w["Costs"][0] == cost}
        else:
            solutions = {tuple(sorted(w['Value'])) for w in witnesses}
    return output['Result'], solutions

def test_instance(args, instance):
    # set options
    if args.optimize:
        options = [args.encoding, args.instances + instance, "--opt-mode=optN"]
    else:
        options = [args.encoding, args.instances + instance, "925"] # max 925 answers
    # call clingo and get solutions
    stdout, time = call_clingo(args.clingo, options, args.timeout)
    result, solutions = get_solutions(args, json.loads(stdout))
    # print("output:")
    # print(result)
    # print(solutions)
    # get reference solutions
    inst_sol = instance[:-2] + "json"
    with open(args.solutions + inst_sol, "r") as infile:
        ref_result, ref_solutions = get_solutions(args, json.load(infile))
    # print("reference:")
    # print(ref_result)
    # print(ref_solutions)
    # compare solution with reference solution
    if result != ref_result: # is the same result?
        return False, time  
    if solutions == []:      # if unsat then return
        return True, time
    return solutions == ref_solutions, time

def test(args):
    # read instances and sort them
    instances_dir = os.listdir(args.instances)
    instances_dir.sort()
    # loop over instances
    success = True
    for instance in instances_dir:
        message = f"{instance}: "
        try:
            result, time = test_instance(args, instance)
            if result:
                message += f"success in {time:.3f} seconds"
            else:
                success = False
                message += f"failure in {time:.3f} seconds"
        except TimeoutExpired as e:
            success = False
            if isinstance(e, TimeoutExpired):
                message +=  "failure: timeout"
            else:
                message += f"failure: error: {str(e)}"
        print(message)
    if success: print("SUCCESS")
    else: print("FAILURE")

def parse():
    parser = argparse.ArgumentParser(
        description="Test ASP encodings"
    )
    parser.add_argument('--encoding', '-e', metavar='<file>',
                        help='ASP encoding to test', required=True)
    parser.add_argument('--timeout', '-t', metavar='N', type=int,
                        help='Time allocated to each instance', required=True)
    parser.add_argument('--instances', '-i', metavar='<path>',
                        help='Directory of the instances', default="asp/instances/", required=False)
    parser.add_argument('--solutions', '-s', metavar='<path>',
                        help='Directory of the solutions', default="asp/solutions/", required=False)
    parser.add_argument('--clingo', '-c', metavar='<path>',
                        help='Clingo binary', default="clingo", required=False)
    parser.add_argument('--optimize', '-opt', action='store_const', const=True,
                        help='Use this option for optimization problems', default=False, required=False)
    args = parser.parse_args()
    if shutil.which(args.clingo) is None:
        raise IOError("file %s not found!" % args.clingo)
    if not os.path.isfile(args.encoding):
        raise IOError("file %s not found!" % args.encoding)
    if not os.path.isdir(args.instances):
        raise IOError("directory %s not found!" % args.instances)
    if not os.path.isdir(args.solutions):
        raise IOError("directory %s not found!" % args.solutions)
    if args.instances[-1] != "/":
        args.instances+="/"
    if args.solutions[-1] != "/":
        args.solutions+="/"
    return args

def main():
    if sys.version_info < (3, 5):
        raise SystemExit('ERROR: This program requires Python 3.5 or higher')
    test(parse())

if __name__ == '__main__':
    sys.exit(main())
