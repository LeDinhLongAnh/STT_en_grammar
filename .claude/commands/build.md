---
description: Configure, build and test the project with MSVC
---

Build the project and run the unit tests, then report the outcome.

1. If `third_party/sherpa-onnx/include/sherpa-onnx/c-api/c-api.h` is missing,
   run `bash scripts/fetch_sherpa_onnx.sh` first.
2. Configure and build. On Windows the compiler is not on PATH by default, so
   go through `vcvars64.bat`:

   ```
   powershell -NoProfile -Command "$vs='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'; cmd /c \"call `\"$vs`\" >nul 2>nul && cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build --parallel\""
   ```

   `scripts\build.bat Release test` does the same thing from cmd.exe.
3. Run `./build/bin/vcc_tests.exe`.
4. Report: any compiler warnings (the tree is `/W4` clean, so a new warning is a
   regression), and the pass/fail line. If tests fail, show the failing
   assertion rather than summarising it.
