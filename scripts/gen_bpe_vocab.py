#!/usr/bin/env python3
"""Dump a sentencepiece model as the piece/score table sherpa-onnx wants.

sherpa-onnx does not link sentencepiece itself; it ships a small greedy
segmenter (ssentencepiece) that reads exactly this two-column
"piece<TAB>score" file and uses the scores to pick a segmentation. Feeding it a
table derived from the real bpe.model is what makes word-level hotwords line up
with the decoder's own subword output.

    python scripts/gen_bpe_vocab.py models/<id>/bpe.model models/<id>/bpe.vocab
"""
import sys


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        import sentencepiece as spm
    except ImportError:
        print("need sentencepiece: pip install sentencepiece", file=sys.stderr)
        return 3

    sp = spm.SentencePieceProcessor(model_file=argv[1])
    with open(argv[2], "w", encoding="utf-8", newline="\n") as f:
        for i in range(sp.get_piece_size()):
            f.write("{}\t{}\n".format(sp.id_to_piece(i), sp.get_score(i)))
    print("wrote {} pieces to {}".format(sp.get_piece_size(), argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
