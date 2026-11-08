/*
 *  testlib.h  --  a small, self contained subset of the well known TestLib.
 *
 *  It is used to compile user supplied "custom checker" programs.  The
 *  checker is called as
 *
 *      checker <input file> <output file> <answer file>
 *
 *  and signals its verdict through the exit code:
 *
 *      0  accept            1  wrong answer       2  presentation error
 *      3  failure           4  dirty output       5  unknown error
 *
 *  Supported API (a subset of TestLib):
 *
 *      inf / ouf / ans / INF / OUF / ANS
 *          .readEof()  .seekEof()  .readToken()  .readString()  .readWord()
 *          .readInt()  .readLong()  .readReal()  .readInt(n)  .readLine()
 *      quitf(status, format, ...)   quit(status, format, ...)
 *      _ok _wa _pe _fail _dirt _points
 */
#ifndef MINI_TESTLIB_H
#define MINI_TESTLIB_H

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cctype>
#include <cmath>
#include <string>
#include <iostream>
#include <fstream>
#include <sstream>

enum TStatus {
    _ok = 0,
    _wa = 1,
    _pe = 2,
    _fail = 3,
    _dirt = 4,
    _points = 5
};

struct QuitException {
    int status;
    std::string message;
    QuitException(int s, const std::string& m) : status(s), message(m) {}
};

inline void quit(int status, const char* format, ...) {
    char buffer[4096];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    throw QuitException(status, std::string(buffer));
}

inline void quitf(int status, const char* format, ...) {
    char buffer[4096];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    throw QuitException(status, std::string(buffer));
}

/* --------------------------------------------------------------------- */
/*  stream classes                                                        */
/* --------------------------------------------------------------------- */
class BaseStream {
protected:
    std::istream* stream;
    std::string name;
    bool opened;

    void ensureOpen() {
        if (!opened) {
            quitf(_fail, "Cannot open file '%s'", name.c_str());
        }
    }

public:
    BaseStream() : stream(NULL), opened(false) {}
    explicit BaseStream(const char* fileName) : stream(NULL), name(fileName ? fileName : ""), opened(false) {
        if (fileName && *fileName) {
            std::ifstream* in = new std::ifstream(fileName);
            if (in->is_open()) {
                stream = in;
                opened = true;
            } else {
                delete in;
            }
        }
    }
    virtual ~BaseStream() { delete stream; }

    bool seekEof() {
        ensureOpen();
        int c = stream->get();
        while (c != EOF && isspace(static_cast<unsigned char>(c))) {
            c = stream->get();
        }
        if (c == EOF) {
            return true;
        }
        stream->unget();
        return false;
    }

    void readEof() {
        if (!seekEof()) {
            quitf(_wa, "Expected end of file in '%s'", name.c_str());
        }
    }

    std::string readToken() {
        ensureOpen();
        std::string token;
        if (!(stream >> token)) {
            quitf(_wa, "Unexpected end of file in '%s'", name.c_str());
        }
        return token;
    }

    std::string readWord() { return readToken(); }
    std::string readString() { return readToken(); }

    std::string readLine() {
        ensureOpen();
        std::string line;
        std::getline(*stream, line);
        while (!line.empty() && (line[line.size() - 1] == '\r')) {
            line.erase(line.size() - 1);
        }
        return line;
    }

    long long readLong() {
        std::string token = readToken();
        errno = 0;
        char* end = NULL;
        long long value = strtoll(token.c_str(), &end, 10);
        if (end == token.c_str() || (end && *end != '\0') || errno == ERANGE) {
            quitf(_wa, "Expected an integer, got '%s'", token.c_str());
        }
        return value;
    }

    int readInt() { return static_cast<int>(readLong()); }

    int readInt(int digits) {
        int result = 0;
        for (int i = 0; i < digits; ++i) {
            std::string token = readToken();
            if (token.size() != 1 || !isdigit(static_cast<unsigned char>(token[0]))) {
                quitf(_wa, "Expected a digit, got '%s'", token.c_str());
            }
            result = result * 10 + (token[0] - '0');
        }
        return result;
    }

    double readReal() {
        std::string token = readToken();
        char* end = NULL;
        double value = strtod(token.c_str(), &end);
        if (end == token.c_str() || (end && *end != '\0')) {
            quitf(_wa, "Expected a real number, got '%s'", token.c_str());
        }
        return value;
    }

    std::istream& raw() { ensureOpen(); return *stream; }
};

class InStream : public BaseStream {
public:
    InStream() {}
    explicit InStream(const char* fileName) : BaseStream(fileName) {}
};

class OutStream : public BaseStream {
public:
    OutStream() {}
    explicit OutStream(const char* fileName) : BaseStream(fileName) {}
    void write(const std::string& text) {
        ensureOpen();
        *stream << text;
    }
    void writeLine(const std::string& text) {
        ensureOpen();
        *stream << text << std::endl;
    }
};

/* --------------------------------------------------------------------- */
/*  global streams                                                        */
/* --------------------------------------------------------------------- */
inline InStream& getInf(const char* fileName) {
    static InStream instance(fileName);
    return instance;
}
inline OutStream& getOuf(const char* fileName) {
    static OutStream instance(fileName);
    return instance;
}

#ifndef INF
#define INF (getInf("input.txt"))
#endif
#ifndef OUF
#define OUF (getOuf("output.txt"))
#endif
#ifndef ANS
#define ANS (getInf("answer.txt"))
#endif

/* --------------------------------------------------------------------- */
/*  helpers                                                               */
/* --------------------------------------------------------------------- */
inline bool almostEqual(double a, double b, double eps = 1e-6) {
    double diff = fabs(a - b);
    if (diff <= eps) {
        return true;
    }
    double scale = fabs(a) > fabs(b) ? fabs(a) : fabs(b);
    return diff <= eps * (scale > 1.0 ? scale : 1.0);
}

inline void ensureMaxOutputSize(long long size, long long limit) {
    if (limit > 0 && size > limit) {
        quitf(_dirt, "The output is too big: %lld bytes (limit %lld)", size, limit);
    }
}

#endif  /* MINI_TESTLIB_H */
