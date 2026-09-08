// The hotword list: the vocabulary we force into the decoder.
//
// This is the whole point of the project. A general-purpose English recogniser
// has no idea that "guest network" is more likely than "guess network" in this
// context, and for a Vietnamese speaker whose final consonants are soft, that
// prior is the difference between working and not working. Contextual biasing
// hands the decoder that prior *before* it commits to a hypothesis.
//
// **One boost for the whole list.** sherpa-onnx accepts a per-phrase score, and
// this project deliberately does not use it: a per-phrase knob is a per-phrase
// decision, and there is no way to make thirty of those well. One number is
// tunable against a corpus in an afternoon; thirty are not. A line carrying an
// old ":2.5" suffix is accepted and the score ignored, with a warning, so an
// existing file does not silently change meaning.
//
// Two things make this list special compared to a plain vector<string>:
//
//   * It is **per-decode**, not per-model. sherpa-onnx accepts hotwords on the
//     stream as well as in the recogniser config, so the list can change
//     between two decodes of the same audio with no model reload. That is what
//     lets the dashboard show "before" and "after" side by side, and what makes
//     tuning interactive instead of a 2-second round trip.
//   * It has a **wire format with a trap in it**. See Serialize().
#pragma once

#include <string>
#include <vector>

namespace vcc {

struct Hotword {
  std::string phrase;  // as written by the user
  int line = 0;        // source line, for error messages
};

class HotwordList {
 public:
  // Parses config/hotwords.txt: one phrase per line, '#' comments. Returns
  // false only if the file cannot be read.
  bool LoadFile(const std::string &path, std::vector<std::string> *warnings = nullptr);

  // Replaces the list from a plain text blob in the same format. This is how
  // the dashboard pushes an edited list without touching the file.
  void LoadText(const std::string &text, std::vector<std::string> *warnings = nullptr);

  // The text form, round-trippable through LoadText. What the dashboard edits.
  std::string ToText() const;

  // Serialises for sherpa-onnx's *per-stream* hotwords argument, applying
  // `boost` to every phrase.
  //
  // THE TRAP: the per-stream API splits on '/', not on newline
  // (offline-recognizer-transducer-impl.h does a regex_replace of "/" -> "\n"
  // before parsing). A phrase containing '/' would silently become two
  // hotwords, so Serialize() drops those phrases and reports them.
  //
  // Phrases are uppercased because the English BPE inventories these models
  // ship with are uppercase; a lowercase hotword encodes to nothing useful.
  std::string Serialize(float boost,
                        std::vector<std::string> *warnings = nullptr) const;

  const std::vector<Hotword> &entries() const { return entries_; }
  size_t size() const { return entries_.size(); }
  bool empty() const { return entries_.empty(); }
  void clear() { entries_.clear(); }

  void Add(const std::string &phrase);

  // Longest phrase in words. Useful as a sanity check: a hotword longer than
  // the utterances you expect is a hotword that will never fire.
  size_t max_words() const;

 private:
  std::vector<Hotword> entries_;
};

}  // namespace vcc
