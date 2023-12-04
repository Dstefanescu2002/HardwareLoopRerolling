from collections import defaultdict

# naive way to build suffix array
def suffix_array(s):
    return sorted(range(len(s)), key=lambda i: str(s[i:]))

# find all longest common prefixes in string s
def lcp_array(s, sa):
    # Kasai et al's algorithm:
    # (https://gist.github.com/prasoon2211/cc3f3d5b43a0885c0e7a)
    n = len(s)
    k = 0
    lcp = [0] * n
    rank = [0] * n
    for i in range(n):
        rank[sa[i]] = i
    for i in range(n):
        if rank[i] == n-1:
            k = 0
            continue
        j = sa[rank[i] + 1]
        while i + k < n and j + k < n and s[i + k] == s[j + k]:
            k += 1
        lcp[rank[i]] = k;
        if k:
            k -= 1
    return lcp

def print_suffix_info(s, sa, lcp):
    print(f'\n{s}\n')
    for index, i in enumerate(sa):
        print(f'{i}\t{lcp[index]}\t{s[i:]}')

# longest repeating substring
def lrs(s, sa, lcp):
    max_lcp = max(lcp)
    max_index = max(range(len(lcp)), key=lcp.__getitem__)
    return s[sa[max_index] : sa[max_index] + max_lcp]

def maximal_repeats(s, sa, lcp):
    maxrep = defaultdict(int)
    for i in range(len(s)):
        maxrep[i] = len(s) + 1
    for i in range(len(s)-1):
        p = max(lcp[i], lcp[i+1])
        maxrep[sa[i] + p - 1] = min(maxrep[sa[i] + p - 1], sa[i])
    return maxrep

# given: a token stream (s), suffix array of s (sa), and list of longest common prefixes in s (lcp),
# return: dictionary of tandem repeats in s, mapping repeated token sequence to pair of (start index, number of repeats)
def tandem_repeats(s, sa, lcp):
    tandem_repeats = {}
    for i, suffix_index in enumerate(sa):
        repeat = s[suffix_index:suffix_index + lcp[i]]
        if not repeat:
            continue
        for j in range(0, len(sa)):
            suffix = s[sa[j]:]
            repeats = 1
            try:
                repeat_start = suffix.index(repeat[0])
            except ValueError:
                continue
            while True:
                if repeat * repeats != suffix[repeat_start:repeat_start + len(repeat) * repeats]:
                    break
                repeats += 1
            repeats -= 1
            if repeats > 1:
                if repeat in tandem_repeats and tandem_repeats[repeat][1] > repeats:
                    continue
                tandem_repeats[repeat] = (sa[j] + repeat_start, repeats)
    return tandem_repeats
