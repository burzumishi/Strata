// The tool-name trie without a GPU (src/dsv41/ds4_toolname.hpp, DS4_TOOL_TRIE): the scan that sees a call's name, the
// tokens a name prefix allows, and the server's hex key.
//   ds4_toolname_test        exit 0: all passed
#include "ds4_toolname.hpp"

#include <cstdio>
#include <string>
#include <vector>

namespace tn = strata::ds4::toolname;

static int fails = 0;
#define CHECK(c)                                                           \
    do {                                                                   \
        if (!(c)) {                                                        \
            std::printf("FAIL line %d: %s\n", __LINE__, #c);               \
            ++fails;                                                       \
        }                                                                  \
    } while (0)

static bool has(const std::vector<int>& v, int x) {
    for (int y : v)
        if (y == x) return true;
    return false;
}

int main() {
    // the scan: openings split across tokens, the three forms, the close
    tn::Scan s;
    tn::feed(s, "text before <");
    CHECK(!s.in);
    tn::feed(s, "｜DSML｜ invoke na");
    CHECK(!s.in);
    tn::feed(s, "me=\"read_");
    CHECK(s.in && s.close == '"' && s.pre == "read_");
    tn::feed(s, "file\">");
    CHECK(!s.in && s.pre.empty());
    tn::feed(s, "<function=");
    CHECK(s.in && s.close == '>');
    tn::feed(s, "grep>\n");
    CHECK(!s.in);
    tn::feed(s, "invoke name='x");
    CHECK(s.in && s.close == '\'' && s.pre == "x");
    tn::Scan long_name;
    tn::feed(long_name, "invoke name=\"" + std::string(600, 'a'));
    CHECK(!long_name.in);   // no name is that long

    // the trie: prefixes, a whole name, the close after it, a name that is a prefix of another
    tn::Trie t;
    t.set({"read_file", "read_files", "grep", "mcp__vibecode__search_session_transcripts", "", "grep"});
    CHECK(t.names().size() == 4);
    CHECK(t.prefix("read_f") && t.prefix("") && !t.prefix("reed") && t.full("read_file") && !t.full("read_"));
    CHECK(t.fits("", '"', "read") && t.fits("read", '"', "_file") && t.fits("read_file", '"', "\">"));
    CHECK(t.fits("read_file", '"', "s\""));   // read_files, closed in the same token
    CHECK(!t.fits("read_", '"', "\""));       // closing a name that is not whole
    CHECK(!t.fits("", '"', "reed"));
    CHECK(!t.fits("", '"', ""));              // a special token (no text) never goes inside a name
    CHECK(t.fits("mcp__vibecode__search_session_trans", '"', "cripts"));
    CHECK(!t.fits("mcp__vibecode__search_session_trans", '"', "racts"));   // 2026-11-09's misspelling

    // allowed(): over a small vocabulary
    const std::vector<std::string> txt = {"", "read", "_file", "\"", "\">", "s", "reed", "grep", "g", "_files", "x", "\" "};
    const std::vector<int>& a0 = t.allowed(txt, "", '"');
    CHECK(has(a0, 1) && has(a0, 7) && has(a0, 8) && !has(a0, 0) && !has(a0, 6) && !has(a0, 3) && !has(a0, 10));
    const std::vector<int>& a1 = t.allowed(txt, "read_file", '"');
    CHECK(has(a1, 3) && has(a1, 4) && has(a1, 5) && has(a1, 11) && !has(a1, 2) && !has(a1, 1));
    const std::vector<int>& a2 = t.allowed(txt, "read", '"');
    CHECK(has(a2, 2) && has(a2, 9) && !has(a2, 3));
    const std::vector<int>& a3 = t.allowed(txt, "zzz", '"');
    CHECK(a3.empty());   // nothing fits: the caller leaves the row alone
    // the cache keeps a prefix's answer; new names drop it
    CHECK(&t.allowed(txt, "", '"') == &a0);
    t.set({"other"});
    CHECK(t.allowed(txt, "", '"').empty());

    // the server's key
    std::vector<std::string> names;
    CHECK(tn::parse_hex("726561645f66696c650a6d63705f5f785f5f6c697374", names) && names.size() == 2 &&
          names[0] == "read_file" && names[1] == "mcp__x__list");
    CHECK(!tn::parse_hex("7g", names) && names.empty());
    CHECK(!tn::parse_hex("abc", names));
    CHECK(tn::parse_hex("", names) && names.empty());

    std::printf(fails ? "FAILED: %d\n" : "toolname_test: all passed\n", fails);
    return fails ? 1 : 0;
}
