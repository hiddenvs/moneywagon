from __future__ import print_function

import math
import datetime
from hashlib import sha256
import random

def make_unit(bytes):
    if 1024 > bytes:
        return bytes, "B"
    elif 1048576.0 > bytes > 1024:
        return bytes / 1024.0, "KB"
    elif 1073741824 > bytes > 1048576.0:
        return bytes / 1048576.0, 'MB' # 1024 ** 2
    elif 1073741824 < bytes:
        return bytes / 1073741824.0, 'GB' # 1024 ** 3

def _make_txid(seed=''):
    return sha256(str(random.random()) + str(seed)).hexdigest()

def make_mempool(mb=8, kb=None, verbose=False):
    if verbose:
        t0 = datetime.datetime.now()

    if kb:
        n = int(kb * 1024.0 / 266)
    else:
        n = int(mb * 1024.0 * 1024.0 / 266)

    mempool = []
    for i in xrange(n):
        mempool.append(_make_txid(i))

    if verbose:
        print("generated %s %s mempool with %s transactions, took: %s" % (
            kb or mb,
            'KB' if kb else 'MB',
            len(mempool),
            datetime.datetime.now() - t0
        ))
    actual_size = len(set(mempool))
    assert actual_size == n, "%s != %s" % (actual_size, n)
    return mempool

def get_start_length(size):
    start_length = 1
    while True:
        if float(size) / (16 ** (start_length)) < 1:
            return start_length
        else:
            start_length += 1

def calculate_skip(target, start_length, length):
    return int(
        int(target[:start_length], 16) / float(16 ** start_length) * length
    )

def find_index_fast(target, sorted_base16, length, start_length=4, verbose=False):
    start_length += 3
    if len(target) < start_length:
        start_length = len(target)

    target_value = int(target[:start_length], 16)
    index_guess = int(round(target_value / float(16 ** start_length) * length))
    finds = []

    #print("trying to find:", target)
    #print("initial guess:", index_guess)

    while True:
        if index_guess + 1 >= length:
            index_guess = length - 1

        found = sorted_base16[index_guess]

        if verbose: print("iterating:", index_guess)

        if index_guess in finds:
            # oscilation discovered, iterate between osciliation points
            prev = finds[-1]
            avg = int((prev + index_guess) / 2)
            j = 0
            while True:
                if verbose: print("oscilation iteration", j)
                if avg + j < length:
                    ret = avg + j
                    if sorted_base16[ret].startswith(target):
                        break
                if avg - j > 0:
                    ret = avg - j
                    if sorted_base16[ret].startswith(target):
                        break
                j += 1
                if j > 400:
                    #print("didn't find:", target)
                    return None

            if verbose: print(
                "found", found[:start_length], "after", len(finds), "iterations",
                "and", j, "oscilation iterations."
            )
            return ret

        finds.append(index_guess)

        if found.startswith(target):
            if verbose: print("found", found[:start_length], "after", len(finds), "iterations")
            return index_guess
        found_value = int(found[:start_length] or ('f' * start_length), 16)
        found_percentage = found_value / float(16**(start_length))
        off_by = found_value - target_value
        off_by_percentage = off_by / float(16 ** start_length)

        if off_by < 0:
            adjust_by = int(math.floor(off_by_percentage * length))
        else:
            adjust_by = int(math.ceil(off_by_percentage * length))
        index_guess = index_guess - adjust_by

        if index_guess < 0:
            index_guess = 0
        if index_guess > length:
            index_guess = length

index_timer = 0
def get_unique(txid, sorted_mempool, start_length, mempool_length, extra_bytes=1):
    global index_timer
    t0 = datetime.datetime.now()
    index = find_index_fast(txid, sorted_mempool, mempool_length, start_length)
    index_timer += (datetime.datetime.now() - t0).total_seconds()

    if index == 0:
        before = ''
    else:
        before = sorted_mempool[index-1]

    if index + 1 >= mempool_length:
        after = ''
    else:
        after = sorted_mempool[index+1]

    i = start_length
    while txid[:i] in (before[:i], after[:i]):
        if False:
            import ipdb; ipdb.set_trace()
            print(
                index, mempool_length, "txid", txid[:i], "before",
                before[:i], "after", after[:i]
            )
        i += 1
        if i > 30:
            raise SystemExit("possible infinite loop")

    return txid[:i+extra_bytes]

def encode_mempool(mempool, extra_bytes=2, verbose=False):
    mempool_length = len(mempool)

    t1 = datetime.datetime.now()
    sorted_mempool = sorted(mempool)
    sorting_time = datetime.datetime.now() - t1

    start_length = get_start_length(mempool_length)

    short_ids = []
    t2 = datetime.datetime.now()
    for tx in mempool:
        short_ids.append(
            get_unique(
                tx, sorted_mempool,
                start_length=start_length, mempool_length=mempool_length,
                extra_bytes=extra_bytes
            )
        )
    encoding_time = datetime.datetime.now() - t2

    t3 = datetime.datetime.now()
    hash = sha256(''.join(x for x in mempool)).hexdigest()
    hash_time = datetime.datetime.now() - t3

    if verbose:
        print("encoding mempool took: %s" % encoding_time)
        print("sorting mempool took: %s" % sorting_time)
        print("using start length of: %s" % start_length)

        size = sum(len(x) for x in short_ids)
        avg_bytes_per_tx = size / float(mempool_length)
        print("average bytes per tx: %.4f" % avg_bytes_per_tx)

        total_weight = size + mempool_length + 64
        print("total weight: %.2f %s" % make_unit(total_weight))

        mempool_size = ((mempool_length * 266.0) / 1048576)
        print(
            "compression percentage: %.2f%%" % (
                100 - (100.0 * (total_weight / mempool_size / (1024 ** 2)))
            )
        )

        print("encoding speed: %.2f tps" % (
            float(mempool_length) / encoding_time.total_seconds()
        ))
        #print("length of set: %s" % len(set(short_ids)))
        print("unique encoding?: %s" % (len(set(mempool)) == mempool_length))

        global index_timer
        print("seconds spent finding index: %.2f (%.2f%%)" % (index_timer, (100.0 * index_timer/encoding_time.total_seconds() )))
        index_timer = 0

        print("time to make hash: %s" % hash_time)

    return short_ids, hash

def get_full_id(short_id, sorted_base16, length, verbose=False):
    index = find_index_fast(short_id, sorted_base16, length, 5, verbose=False)
    if index is None:
        return None

    finds = [sorted_base16[index]]

    forward = lambda i: index + i
    backward = lambda i: index - i
    greater_than_zero = lambda try_: try_ > 0
    less_than_end = lambda try_: try_ < length

    for direction, under_limit in [[forward, less_than_end], [backward, greater_than_zero]]:
        i = 1
        while True:
            try_ = direction(i)
            if not under_limit(try_):
                break
            find = sorted_base16[try_]
            if find.startswith(short_id):
                if verbose: print("dupe found", find)
                finds.append(find)
                i += 1
                continue

            break

    return finds

def decode_superthin_chunk(short_ids, sorted_mempool, length, verbose=False):
    full_ids = []
    duplicates = []
    missing = []
    for i, short_id in enumerate(short_ids):
        found = get_full_id(short_id, sorted_mempool, length, verbose=verbose)
        if not found:
            if verbose: print("position %s missing: %s" % (i, short_id))
            full_ids.append(short_id)
            missing.append(short_id)
        elif len(found) > 1:
            if verbose:
                print("found %s candidates at position %s: %s" % (
                    len(found), i,
                    ', '.join("%s..." % x[:10] for x in found)
                ))
            full_ids.append("dupe")
            duplicates.append(found)
        else:
            full_ids.append(found[0])

    return full_ids, missing, duplicates

def prod(iterable):
    p = 1
    for n in iterable:
        p *= n
    return p

def all_combinations(duplicates, i=0):
    if i >= prod(len(x) for x in duplicates):
        return None # all combinations have been tried
    this_pass = []
    for item in duplicates:
        l = len(item)
        this_i = i % l
        i = int(i / l)
        this_pass.append(item[this_i])

    return this_pass

def decode_superthin(short_ids, mempool, hash, threads=4, verbose=False):
    smp = sorted(mempool)

    full_ids, missing, duplicates = decode_superthin_chunk(
        short_ids, smp, len(mempool), verbose=verbose
    )
    if missing:
        if verbose:
            print("Missing transactions, can't continue")
            return # todo: fetch misssing
    elif verbose:
        print("No missing txids!")

    if duplicates:
        i = 0
        total_tries = prod(len(x) for x in duplicates)
        if total_tries > 1500:
            if verbose: print("too many duplicates, %s tries required" % total_tries)
            return None

        while True:
            group = all_combinations(duplicates, i)
            if not group:
                if verbose: print("Tried all duplicate groups: decode failed")
                return None # decode failed
            if verbose: print("Trying duplicate group %s" % i)
            this_try = []
            hash_try = sha256()
            group.reverse()
            for j, txid in enumerate(full_ids):
                if txid == 'dupe':
                    try_ = group.pop()
                    if verbose: print("trying %s... at position %s" % (try_[:10], j))
                    this_try.append(try_)
                    hash_try.update(try_)
                else:
                    this_try.append(txid)
                    hash_try.update(txid)

            if hash_try.hexdigest() == hash:
                if verbose: print("Group %s suceeded!" % i)
                return full_ids
            i += 1

    elif verbose:
        print("Found no duplicates!")

    decoded_hash = sha256(''.join(full_ids)).hexdigest()
    if decoded_hash == hash:
        if verbose: print("Hash succeeded!")
        return full_ids
    else:
        if verbose: print("Hash failed?")
        return None

if __name__ == '__main__':
    def modify_mempool(mempool, remove=10, add=10, verbose=False):
        """
        Given a list of txids (mempool), add and remove some items to simulate
        an out of sync mempool.
        """
        for i in range(remove):
            popped = mempool.pop()
            if verbose: print("removed:", popped)

        for i in range(add):
            new_txid = _make_txid()
            mempool.append(new_txid)
            if verbose: print("added:", new_txid)

        return mempool

    def test_fast_index_finder(mp=None, partial=False):
        if not mp:
            mp = make_mempool(mb=32, verbose=True)
        smp = sorted(mp)
        l = len(mp)
        t0 = datetime.datetime.now()
        for i, txid in enumerate(smp):
            if partial:
                txid = txid[:8]
            result = find_index_fast(txid, smp, l, start_length=4)
            if not result == i:
                print("wrong index returned %s %s" % (result, i))
        print("optimized", datetime.datetime.now() - t0)

    def compare_index_finders(from_file=False):
        if from_file:
            mp = _get_mempool_from_file()
        else:
            mp = make_mempool(mb=32)
        test_fast_index_finder(mp)
        t0 = datetime.datetime.now()
        for i, txid in enumerate(mp):
            smp.index(txid)
        print("un-optimized", datetime.datetime.now() - t0)

    def _get_mempool_from_file():
        t0 = datetime.datetime.now()
        with open('mp.txt') as f:
            mp = [x.strip() for x in f.readlines()]
        print("loaded mempool from file, took: %s" % (
            datetime.datetime.now() - t0
        ))
        return mp

    def test_from_file(index=None, key=None):
        smp = _get_mempool_from_file()
        if not index and not key:
            for i, txid in enumerate(smp):
                index = find_index_fast(txid, smp, len(smp))
                if i != index:
                    print(i, index)
        elif index:
            result = find_index_fast(smp[index], smp, len(smp))
            print(index, result)
        elif key:
            result = find_index_fast(key, smp, len(smp))
            print(index, result)

    def test_file_encode():
        mp = _get_mempool_from_file()
        random.shuffle(mp)
        encoded, hash = encode_mempool(mp, verbose=True)

    def test_find_index_missing():
        smp = _get_mempool_from_file()
        print(find_index_fast(_make_txid(), smp, len(smp), 5, verbose=True))

    def test_find_duplicate():
        #mp = make_mempool(mb=64)
        mp = _get_mempool_from_file()
        dupe = _make_txid()
        print("dupe is: %s" % dupe)
        mp.append(dupe)
        print(get_full_id(dupe[:4], sorted(mp), len(mp), True))

    def performance_test_encode():
        # testing encoding of large mempools
        for size in [32, 64, 128, 256]:
            mp = make_mempool(mb=size, verbose=True)
            encoded, hash = encode_mempool(mp, verbose=True)
            print("-----")

    def test_not_completely_synced(from_file=False, extra_bytes=1):
        """
        tesing decoding against not completely synced mempools
        """
        if not from_file:
            mp = make_mempool(mb=1, verbose=True)
        else:
            mp = _get_mempool_from_file()
        t0 = datetime.datetime.now()
        encoded, hash = encode_mempool(mp, extra_bytes=extra_bytes, verbose=True)
        encoding_time = datetime.datetime.now() - t0
        print("encoding complete, took: %s" % encoding_time)

        for action in [{'add': 30, 'remove': 3}]:
            action['verbose'] = True
            modified_mempool = modify_mempool(mp, **action)
            t1 = datetime.datetime.now()
            full_ids = decode_superthin(
                encoded, modified_mempool, hash=hash, verbose=True
            )
            decoding_time = datetime.datetime.now() - t1
            print("decoding took: %s" % decoding_time)

    #test_find_duplicate()
    #test_fast_index_finder(partial=True, mp=_get_mempool_from_file())
    test_not_completely_synced(from_file=False, extra_bytes=0)
    #test_find_index_missing()
