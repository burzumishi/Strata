// 2026-11-10 (ds-wormhole, DS4_TOOL_TRIE): a tool call's name kept to the names the request declares - the part that
// needs no GPU.  The model writes a call as DSML (`<｜DSML｜ invoke name="read_file">`) or, now and then, Qwen's form
// (`<function=read_file>`); a misspelt name ("search_session_transracts", "Vibeccode") does not match any declared tool,
// the call comes back as text and the client runs nothing.  Only the engine can stop that, while it writes: inside a
// name, every row of logits keeps only the tokens whose text goes on with a declared name or closes one.  Outside a name
// nothing changes, and a valid output is the same as before.
//   Scan: where the output is, fed byte by byte (the token texts of DS4_TIE_VOCAB).
//   Trie: the declared names and, per name prefix, the token ids allowed next (cached: the same names every turn).
// tests/dsv41/toolname_test.cpp checks them alone.
#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace strata::ds4::toolname {

// The openings a name follows, and what closes it.  The server's parser also reads a name without quotes and with
// spaces around `=` (serve/dsml.py:39); the model writes these forms, and only these are kept.
struct Opening {
    const char* text;
    char close;
};
inline const std::array<Opening, 3>& openings() {
    static const std::array<Opening, 3> o = {{{"invoke name=\"", '"'}, {"invoke name='", '\''}, {"<function=", '>'}}};
    return o;
}

struct Scan {
    bool in = false;   // inside a name
    char close = 0;    // what ends it
    std::string pre;   // the name so far
    std::string tail;  // the last bytes outside a name (to see an opening)
};

inline void feed(Scan& s, const std::string& bytes) {
    for (char b : bytes) {
        if (s.in) {
            if (b == s.close) {
                s.in = false;
                s.pre.clear();
                s.tail.clear();
            } else {
                s.pre.push_back(b);
                if (s.pre.size() > 512) {   // (no name is this long: whatever this is, it is not a call's name)
                    s.in = false;
                    s.pre.clear();
                }
            }
            continue;
        }
        s.tail.push_back(b);
        if (s.tail.size() > 32) s.tail.erase(0, s.tail.size() - 32);
        for (const Opening& o : openings()) {
            const size_t n = std::char_traits<char>::length(o.text);
            if (s.tail.size() >= n && s.tail.compare(s.tail.size() - n, n, o.text) == 0) {
                s.in = true;
                s.close = o.close;
                s.pre.clear();
                s.tail.clear();
                break;
            }
        }
    }
}

class Trie {
public:
    // the request's names (empty ones dropped); the cache is kept while they stay the same
    void set(std::vector<std::string> names) {
        names.erase(std::remove(names.begin(), names.end(), std::string()), names.end());
        std::sort(names.begin(), names.end());
        names.erase(std::unique(names.begin(), names.end()), names.end());
        if (names != names_) {
            names_ = std::move(names);
            cache_.clear();
        }
    }
    const std::vector<std::string>& names() const { return names_; }
    // s is the start of a declared name (or one)
    bool prefix(const std::string& s) const {
        const auto it = std::lower_bound(names_.begin(), names_.end(), s);
        return it != names_.end() && it->compare(0, s.size(), s) == 0;
    }
    bool full(const std::string& s) const { return std::binary_search(names_.begin(), names_.end(), s); }
    // a token whose text, after `pre`, stays on a declared name or closes a whole one (what follows the close is free)
    bool fits(const std::string& pre, char close, const std::string& text) const {
        if (text.empty()) return false;   // (a special token, or one with no text: never inside a name)
        std::string s = pre;
        for (char b : text) {
            if (b == close) return full(s);
            s.push_back(b);
            if (!prefix(s)) return false;
        }
        return true;
    }
    // the ids allowed after `pre` (txt: the token texts by id); empty: nothing fits (the caller leaves the row alone)
    const std::vector<int>& allowed(const std::vector<std::string>& txt, const std::string& pre, char close) {
        const std::string key = std::string(1, close) + pre;
        const auto hit = cache_.find(key);
        if (hit != cache_.end()) return hit->second;
        // the bytes that can come next: a declared name's next byte, or the close after a whole name
        std::array<bool, 256> next{};
        for (const std::string& n : names_)
            if (n.size() > pre.size() && n.compare(0, pre.size(), pre) == 0) next[(unsigned char) n[pre.size()]] = true;
        if (full(pre)) next[(unsigned char) close] = true;
        std::vector<int> ids;
        for (size_t i = 0; i < txt.size(); ++i)
            if (!txt[i].empty() && next[(unsigned char) txt[i][0]] && fits(pre, close, txt[i])) ids.push_back((int) i);
        return cache_.emplace(key, std::move(ids)).first->second;
    }
    // (called where no reference from allowed() is held: past 4096 prefixes the cache starts again)
    void trim() {
        if (cache_.size() > 4096) cache_.clear();
    }

private:
    std::vector<std::string> names_;
    std::unordered_map<std::string, std::vector<int>> cache_;
};

// the server's key: the names joined by '\n', as lowercase hex (no spaces on the GEN line); false: not hex
inline bool parse_hex(const std::string& hex, std::vector<std::string>& names) {
    names.clear();
    if (hex.size() % 2 != 0) return false;
    std::string bytes;
    const auto nib = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < hex.size(); i += 2) {
        const int a = nib(hex[i]), b = nib(hex[i + 1]);
        if (a < 0 || b < 0) return false;
        bytes.push_back((char) (a * 16 + b));
    }
    size_t s = 0;
    for (size_t i = 0; i <= bytes.size(); ++i)
        if (i == bytes.size() || bytes[i] == '\n') {
            if (i > s) names.push_back(bytes.substr(s, i - s));
            s = i + 1;
        }
    return true;
}

}  // namespace strata::ds4::toolname
