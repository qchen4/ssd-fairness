#pragma once

// Cross-platform getopt compatibility layer
// On Unix, use the system getopt.h
// On Windows, provide a minimal implementation

#if defined(_WIN32) || defined(_MSC_VER)

#include <string.h>
#include <stdio.h>

// Minimal getopt implementation for Windows
extern "C" {

static char* optarg = nullptr;
static int optind = 1;
static int opterr = 1;
static int optopt = 0;

struct option {
    const char* name;
    int has_arg;
    int* flag;
    int val;
};

#define no_argument 0
#define required_argument 1
#define optional_argument 2

inline int getopt_long(int argc, char* const argv[], const char* optstring,
                       const struct option* longopts, int* longindex) {
    static int sp = 1;
    
    if (optind >= argc || argv[optind] == nullptr) {
        return -1;
    }
    
    const char* arg = argv[optind];
    
    // Check for long option
    if (arg[0] == '-' && arg[1] == '-' && arg[2] != '\0') {
        const char* opt_name = arg + 2;
        const char* eq = strchr(opt_name, '=');
        size_t name_len = eq ? (size_t)(eq - opt_name) : strlen(opt_name);
        
        for (int i = 0; longopts && longopts[i].name; ++i) {
            if (strncmp(longopts[i].name, opt_name, name_len) == 0 &&
                strlen(longopts[i].name) == name_len) {
                
                if (longindex) *longindex = i;
                
                if (longopts[i].has_arg == required_argument) {
                    if (eq) {
                        optarg = const_cast<char*>(eq + 1);
                    } else if (optind + 1 < argc) {
                        optarg = argv[++optind];
                    } else {
                        if (opterr) fprintf(stderr, "Option '--%s' requires an argument\n", longopts[i].name);
                        optind++;
                        return '?';
                    }
                } else if (longopts[i].has_arg == optional_argument && eq) {
                    optarg = const_cast<char*>(eq + 1);
                } else {
                    optarg = nullptr;
                }
                
                optind++;
                
                if (longopts[i].flag) {
                    *longopts[i].flag = longopts[i].val;
                    return 0;
                }
                return longopts[i].val;
            }
        }
        
        if (opterr) fprintf(stderr, "Unknown option: %s\n", arg);
        optind++;
        return '?';
    }
    
    // Check for short option
    if (arg[0] == '-' && arg[1] != '\0' && arg[1] != '-') {
        char opt = arg[sp];
        const char* p = strchr(optstring, opt);
        
        if (!p) {
            optopt = opt;
            if (opterr) fprintf(stderr, "Unknown option: -%c\n", opt);
            if (arg[++sp] == '\0') {
                optind++;
                sp = 1;
            }
            return '?';
        }
        
        if (p[1] == ':') {
            // Option requires argument
            if (arg[sp + 1] != '\0') {
                optarg = const_cast<char*>(&arg[sp + 1]);
                optind++;
                sp = 1;
            } else if (optind + 1 < argc) {
                optarg = argv[++optind];
                optind++;
                sp = 1;
            } else {
                if (opterr) fprintf(stderr, "Option '-%c' requires an argument\n", opt);
                optind++;
                sp = 1;
                return '?';
            }
        } else {
            optarg = nullptr;
            if (arg[++sp] == '\0') {
                optind++;
                sp = 1;
            }
        }
        
        return opt;
    }
    
    // Not an option
    return -1;
}

} // extern "C"

#else
// Unix - use system getopt
#include <getopt.h>
#endif

