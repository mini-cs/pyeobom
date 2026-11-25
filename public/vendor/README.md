# public/vendor

화면이 쓰는 외부 라이브러리 사본. 받은 그대로 두고 고치지 않는다(2차 Task 6).

## supabase.js

- 무엇: `@supabase/supabase-js` **2.119.2**의 브라우저용 단일 파일 `dist/umd/supabase.js`(패키지 `unpkg`·`jsdelivr` 필드가 가리키는 파일, `window.supabase`로 둠)
- 받은 날: 2026-11-25
- 받은 주소(두 곳에서 받아 같은지 대조):
  - https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.2/dist/umd/supabase.js
  - https://unpkg.com/@supabase/supabase-js@2.119.2/dist/umd/supabase.js
- SHA-256: `8816af04d9915dbba1882d6f84f0b402dc40268063a63d9c66d24f52f371c263` (221,417바이트)
- 라이선스: MIT(npm `license`, 원문은 같은 판의 `LICENSE`, 아래)
- 쓰는 곳: `public/js/auth.js`가 공개 설정을 받은 뒤에만 불러온다(첫 화면에서는 받지 않음)

<details>
<summary>MIT License 원문 (@supabase/supabase-js 2.119.2 LICENSE)</summary>

```
MIT License

Copyright (c) 2020 Supabase

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

</details>
