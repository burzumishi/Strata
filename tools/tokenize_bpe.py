#!/usr/bin/env python3
"""tokenize_bpe.py -- tokeniza texto a IDs con el BPE gpt2 (byte-level) del pack de Strata.

Uso: python3 tokenize_bpe.py "texto a tokenizar" [salida_ids.txt]
El vocab.json y merges.txt se leen de la ruta del tokenizer pasada por --tokenizer o por defecto.
"""
import json
import regex as re
import sys

TOKENIZER_DIR = "~/Strata-data/packs/ista-iq2xs/tokenizer"

# byte-level BPE de GPT-2: byte -> caracter
def bytes_to_unicode():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))

BYTE_ENCODER = bytes_to_unicode()
BYTE_DECODER = {v: k for k, v in BYTE_ENCODER.items()}

PAT = re.compile(
    r"""(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])|[^\r\n\p{L}\p{N}]?[\p{L}\p{M}]+|\p{N}| ?[^\s\p{L}\p{M}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"""
)


def load_bpe(vocab_path, merges_path):
    vocab = json.load(open(vocab_path))          # token -> id
    merges = open(merges_path, encoding="utf-8").read().splitlines()
    if merges and merges[0].startswith("#"):
        merges = merges[1:]
    ranks = {}
    for i, line in enumerate(merges):
        parts = line.split()
        if len(parts) == 2:
            ranks[(parts[0], parts[1])] = i
    return vocab, ranks


def bpe_word(word, ranks):
    chars = list(word)
    while True:
        pairs = set(zip(chars, chars[1:]))
        if not pairs:
            break
        bigram = min(pairs, key=lambda p: ranks.get(p, float("inf")))
        if bigram not in ranks:
            break
        a, b = bigram
        out = []
        i = 0
        while i < len(chars):
            j = chars.index(a, i) if a in chars[i:] else -1
            if j == -1:
                out.extend(chars[i:])
                break
            out.extend(chars[i:j])
            if j < len(chars) - 1 and chars[j + 1] == b:
                out.append(a + b)
                i = j + 2
            else:
                out.append(chars[j])
                i = j + 1
        chars = out
    return chars


def tokenize(text, vocab, ranks):
    ids = []
    for match in PAT.finditer(text):
        piece = match.group(0)
        # byte-level: codificar a bytes y mapear a caracteres del vocabulario
        token_bytes = piece.encode("utf-8")
        encoded = "".join(BYTE_ENCODER[b] for b in token_bytes)
        for sub in bpe_word(encoded, ranks):
            if sub in vocab:
                ids.append(vocab[sub])
            else:
                # fallback: token desconocido -> descomponer en bytes
                for c in sub:
                    ids.append(vocab.get(c, vocab.get("�", 0)))
    return ids


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "Explica brevemente que es la decodificacion especulativa."
    vocab_path = f"{TOKENIZER_DIR}/vocab.json"
    merges_path = f"{TOKENIZER_DIR}/merges.txt"
    vocab, ranks = load_bpe(vocab_path, merges_path)
    ids = tokenize(text, vocab, ranks)
    out = ",".join(map(str, ids))
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(out)
        print(f"{len(ids)} tokens -> {sys.argv[2]}")
    else:
        print(f"{len(ids)} tokens")
        print(out)


if __name__ == "__main__":
    main()
