// The kept-conversation (slot) bookkeeping that needs no GPU: a slot's .meta file (identity, size, tokens, checkpoint
// positions) and the choice of which kept conversation a prompt continues, and from where.  The engine's serve loop
// (ds4_main.cpp) uses these; tests/dsv41/slot_test.cpp checks them alone.
//
// Slot .meta layout (little endian), "DS4META2":
//   u64 magic, u64 identity length, identity bytes, u64 .bin bytes, u64 token count, i32 tokens[],
//   u64 checkpoint count (0..4), i64 checkpoints[], u64 magic
// A conversation that holds pictures (2026-11-10) is "DS4META3": the same, then before the closing magic
//   u64 picture count (1..4096), per picture i64 start, u64 hash (the serve loop's FNV-1a of its size and pixels), u64 span
// A text-only slot stays DS4META2, so an engine from before reads it as it always did (and drops a DS4META3 as foreign).
// The magic at both ends and the .bin size make a half-written or foreign file refused, never read.
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace strata::ds4::slotmeta {

constexpr uint64_t kMagic = 0x324154454d345344ull;    // "DS4META2"
constexpr uint64_t kMagicPics = 0x334154454d345344ull;   // "DS4META3": with pictures

// A picture a kept state holds: where its span starts, its pixels' hash, its span's length in tokens.  The image tokens
// of a prompt are all the same id, so two conversations with other pictures at the same place have the same tokens:
// only (start, hash) tells them apart.
struct Pic {
    int64_t start = 0;
    uint64_t hash = 0;
    uint64_t len = 0;
};

// Written under a temporary name and renamed over `path` (an interrupted write leaves no half file).
inline bool write(const std::string& path, const std::string& identity, const std::vector<int32_t>& toks,
                  uint64_t bytes, const std::vector<int64_t>& cks, const std::vector<Pic>& pics = {}) {
    const std::string tmp = path + ".tmp";
    {
        std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
        const uint64_t il = identity.size(), nt = toks.size(), nc = cks.size(), np = pics.size();
        const uint64_t magic = pics.empty() ? kMagic : kMagicPics;
        f.write((const char*) &magic, 8);
        f.write((const char*) &il, 8);
        f.write(identity.data(), (std::streamsize) il);
        f.write((const char*) &bytes, 8);
        f.write((const char*) &nt, 8);
        f.write((const char*) toks.data(), (std::streamsize) (nt * sizeof(int32_t)));
        f.write((const char*) &nc, 8);
        f.write((const char*) cks.data(), (std::streamsize) (nc * sizeof(int64_t)));
        if (np > 0) {
            f.write((const char*) &np, 8);
            for (const Pic& p : pics) {
                f.write((const char*) &p.start, 8);
                f.write((const char*) &p.hash, 8);
                f.write((const char*) &p.len, 8);
            }
        }
        f.write((const char*) &magic, 8);
        f.flush();
        if (!f) return false;
    }
    std::error_code ec;
    std::filesystem::rename(tmp, path, ec);
    return !ec;
}

// false: foreign (another identity), damaged, cut short, or not plausible (no tokens, more than max_ctx, a checkpoint
// outside the tokens, a picture's span outside them).  `pics` null: a slot with pictures is refused (a caller that does
// not know pictures must never take one back as text).
inline bool read(const std::string& path, const std::string& identity, int64_t max_ctx, std::vector<int32_t>& toks,
                 uint64_t& bytes, std::vector<int64_t>& cks, std::vector<Pic>* pics = nullptr) {
    std::ifstream f(path, std::ios::binary);
    uint64_t m0 = 0, il = 0, nt = 0, nc = 0, m1 = 0;
    if (pics != nullptr) pics->clear();
    if (!f.read((char*) &m0, 8) || (m0 != kMagic && !(m0 == kMagicPics && pics != nullptr)) || !f.read((char*) &il, 8) ||
        il != identity.size())
        return false;
    std::string id(il, '\0');
    if (!f.read(id.data(), (std::streamsize) il) || id != identity) return false;
    if (!f.read((char*) &bytes, 8) || !f.read((char*) &nt, 8) || nt == 0 || nt > (uint64_t) max_ctx) return false;
    toks.resize(nt);
    if (!f.read((char*) toks.data(), (std::streamsize) (nt * sizeof(int32_t))) || !f.read((char*) &nc, 8) || nc > 4)
        return false;
    cks.resize(nc);
    if (!f.read((char*) cks.data(), (std::streamsize) (nc * sizeof(int64_t)))) return false;
    if (m0 == kMagicPics) {
        uint64_t np = 0;
        if (!f.read((char*) &np, 8) || np == 0 || np > 4096) return false;
        pics->resize(np);
        for (Pic& p : *pics)
            if (!f.read((char*) &p.start, 8) || !f.read((char*) &p.hash, 8) || !f.read((char*) &p.len, 8) || p.start < 0 ||
                p.len == 0 || (uint64_t) p.start + p.len > nt)
                return false;
    }
    if (!f.read((char*) &m1, 8) || m1 != m0) return false;
    for (int64_t c : cks)
        if (c <= 0 || (uint64_t) c > nt) return false;
    return true;
}

// The prompt's shared start with a kept state, cut at its first picture that is not the same picture at the same
// place on both sides (the image tokens alone cannot tell): `c` tokens agree as ids, the result is how many count.
inline size_t pic_cut(const std::vector<Pic>& held, const std::vector<Pic>& prompt, size_t c) {
    const auto in = [](const std::vector<Pic>& v, const Pic& q) {
        for (const Pic& x : v)
            if (x.start == q.start && x.hash == q.hash) return true;
        return false;
    };
    for (const Pic& q : held)
        if ((size_t) q.start < c && !in(prompt, q)) c = (size_t) q.start;
    for (const Pic& q : prompt)
        if ((size_t) q.start < c && !in(held, q)) c = (size_t) q.start;
    return c;
}

// A position inside a held picture's span (not at its start): no state can be taken back there - the rest of the
// span would have to be read again without the picture's rows.
inline bool in_span(const std::vector<Pic>& held, size_t k) {
    for (const Pic& q : held)
        if ((size_t) q.start < k && k < (size_t) q.start + q.len) return true;
    return false;
}

// The kept conversation `prompt` continues the furthest, and where: *len is the number of the slot's tokens that are
// the prompt's (0: none).  A conversation the prompt continues whole comes back whole (len == its size); one the prompt
// leaves part way - a retried prompt, a history re-rendered without the earlier reasoning - comes back at its latest
// checkpoint the prompt still agrees with.  Only a match longer than `floor` (what the model itself can go back to)
// counts.  The last prompt token is never covered (a prompt always reads its last token).  Ties keep the earlier slot.
// Pictures (2026-11-10): a slot's pictures and the prompt's must agree up to the match (pic_cut), and a checkpoint inside
// a held picture's span does not count; `ppics` null is a prompt without pictures.
struct Cand {
    const std::vector<int32_t>* tokens;
    const std::vector<int64_t>* cks;
    const std::vector<Pic>* pics = nullptr;
};
inline size_t pick(const std::vector<Cand>& slots, const std::vector<int>& prompt, size_t floor, size_t* len,
                   const std::vector<Pic>* ppics = nullptr) {
    *len = 0;
    if (prompt.size() < 2) return SIZE_MAX;
    static const std::vector<Pic> none;
    const std::vector<Pic>& pp = ppics != nullptr ? *ppics : none;
    size_t best = SIZE_MAX;
    for (size_t i = 0; i < slots.size(); ++i) {
        const std::vector<int32_t>& t = *slots[i].tokens;
        const std::vector<Pic>& sp = slots[i].pics != nullptr ? *slots[i].pics : none;
        const size_t lim = std::min(t.size(), prompt.size() - 1);
        size_t c = 0;
        while (c < lim && t[c] == prompt[c]) ++c;
        c = pic_cut(sp, pp, c);
        size_t u = c == t.size() ? c : 0;
        if (u == 0)
            for (int64_t k : *slots[i].cks)
                if ((size_t) k <= c && (size_t) k > u && !in_span(sp, (size_t) k)) u = (size_t) k;
        if (u > *len && u > floor) {
            best = i;
            *len = u;
        }
    }
    return best;
}

}  // namespace strata::ds4::slotmeta
