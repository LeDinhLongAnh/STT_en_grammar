# Hướng dẫn dùng bảng điều khiển

Bảng điều khiển này tồn tại để trả lời **một** câu hỏi: *STT gốc trả ra cái gì, và
sau bộ lọc của mình nó thành cái gì?*

Mọi thứ khác trên màn hình chỉ để bạn đổi **một** biến rồi quay lại đọc câu trả lời đó.

---

## 1. Chạy lên

```bat
scripts\dashboard.bat
```

Hoặc trực tiếp:

```bat
python dashboard\main.py
```

Dashboard tự khởi động `vcc_engine.exe` rồi tự tắt nó khi bạn đóng cửa sổ. Bạn
không cần chạy engine bằng tay.

**Lần đầu** phải có model và thư viện:

```bat
bash scripts\fetch_sherpa_onnx.sh
bash scripts\download_models.sh
scripts\build.bat Release
```

> Engine chỉ bind vào localhost và **không có xác thực**. Nó là công cụ dev trên
> máy bạn, không bao giờ ship xuống router.

---

## 2. Màn hình có gì

```
┌────────────────────────────────────────┬──────────────────────┐
│  3 utterance(s) | filter changed 2     │  Control  Hotwords   │
│                        [Decode a WAV…] │  Rewrites  Log       │
│ ┌────────────────────────────────────┐ │ ┌──────────────────┐ │
│ │ #3  mic  2.1s  rtf 0.04  [CHANGED] │ │ │ Microphone       │ │
│ │ raw       TURN ON GAS NETWORK      │ │ │ Filter           │ │
│ │ filtered  TURN ON GUEST NETWORK    │ │ │ Model            │ │
│ │ diff      turn on [gas→guest] net… │ │ └──────────────────┘ │
│ │ rules     gas => guest             │ │                      │
│ └────────────────────────────────────┘ │                      │
└────────────────────────────────────────┴──────────────────────┘
        dòng so sánh (cái bạn đọc)            các núm để xoay
```

**Bên trái** là kết quả, mới nhất trên cùng. **Bên phải** là 4 tab điều khiển.

---

## 3. Vòng lặp làm việc

Đây là thứ cả cái tool được thiết kế quanh nó:

```
   nói một câu  →  đọc raw vs filtered  →  sửa danh sách hotword  →  đọc lại
        ↑                                                              │
        └──────────────────────────────────────────────────────────────┘
```

Mũi tên cuối là mũi tên phải **rẻ**, và nó rẻ thật: hotwords được truyền vào
decoder **theo từng lần decode**, không nằm trong config của model. Nên khi bạn
bấm Apply ở tab Hotwords, engine **decode lại toàn bộ audio đã thu** với danh
sách mới — **không load lại model**, không chờ 2 giây, và **bạn không phải nói lại**.

Đó là khác biệt giữa một công cụ để *tinh chỉnh* và một công cụ chỉ để *demo*.

Engine giữ lại 40 câu gần nhất **kèm audio** chính là để phục vụ việc này.

---

## 4. Tab Control

### Microphone

- Chọn thiết bị thu. Nhãn hiện kèm sample rate và số kênh.
- **Record** → nói **một câu** → **Stop and decode**. Phím **Space** cũng bấm được.
- **Discard**: dừng mà không decode.
- **Vạch mức** (level meter): thang −60…0 dBFS. Dòng chữ dưới nó sẽ nhắc khi bạn
  nói quá nhỏ hoặc bị clip. Đọc nó đi — *audio vào tệ thì không có hotword nào cứu được*.
- Không có VAD, và đó là chủ ý: **bạn** quyết định câu bắt đầu và kết thúc ở đâu.
  Điều đó cần thiết để so sánh công bằng, và cần thiết nếu clip sẽ đi vào bộ
  corpus đánh giá.

### Filter

Hai tầng của bộ lọc, bật/tắt độc lập:

| | Tầng | Làm gì |
|---|---|---|
| **Stage 1** | Contextual biasing | Ép hotwords **vào trong decoder**, lúc đang beam search |
| **Stage 2** | Rewrite rules | Sửa văn bản **sau khi** đã decode xong |

Tắt Stage 1 là cách nhanh nhất để xem baseline thật.

> Nếu ô Stage 1 bị **mờ (disabled)**, model đang load không bias được. Dòng chữ
> đỏ ngay dưới sẽ nói rõ lý do. Xem mục 8.

### Hotword boost

**Một con số cho cả danh sách.** Không có điểm riêng cho từng cụm từ — cố ý:
ba mươi cái núm thì không ai tinh chỉnh nổi.

**Không có giá trị tốt phổ quát.** Đây là điều quan trọng nhất trong tài liệu này:

| model | boost 0.5–2.0 | 3.0 | 4.0 | 12.0 |
|---|---|---|---|---|
| `zipformer-small-en` | LAMPS | **LAMBS** | LAMBS | LAMBS |
| `zipformer-en` (medium) | LAMPS | LAMPS | LAMPS | LAMPS |

Cùng một hotword `YELLOW LAMBS`, cùng một clip nói "yellow lamps". Model medium
**không bao giờ nhường từ đó**, ở bất kỳ mức boost nào. Nhưng biasing trên nó
không hỏng — `SQUALID QUARTERS`, `THE BROTHERS`, `EARLY NIGHTFALLS` đều bẻ được
ở 4.0.

Lý do: model chính xác hơn thì **tự tin hơn**, nên cùng một mức boost mua được
ít hơn. Và mức đề kháng còn khác nhau **theo từng từ** trên cùng một model.

**Hệ quả thực tế: đổi model là phải sweep lại boost.** Đừng mang con số của
model này sang model khác.

Hai hướng sai đều có giá:

- **Quá thấp**: không có gì đổi. Vô hại, chỉ vô dụng.
- **Quá cao**: decoder bắt đầu **nặn từ vựng của bạn ra từ tiếng ồn**. Cái này
  tệ hơn không bias, vì nó sai một cách *âm thầm và tự tin*.

### Quá cao có thể **xoá từ**, không chỉ thay từ

Cùng một clip, 4 probe, boost 4.0:

| model | kết quả |
|---|---|
| `zipformer-small-en` | thay đúng chỗ, **giữ nguyên số từ** |
| `zipformer-en` (medium) | thay 3/4, giữ nguyên số từ |
| `streaming-zipformer` | `nightfall the yellow lamps` → `nightfalls` — **mất 3 từ** |

Encoder chunk-wise không có right-context để phản biện một đường đã được boost
mạnh, nên nó chốt luôn và **đánh rơi những từ theo sau**. Xoá từ tệ hơn thay từ.

Nên khi tune: **nhìn cả độ dài của dòng `filtered`**, đừng chỉ nhìn từ nào đổi.
Câu ngắn đi bất thường là dấu hiệu boost quá cao.

Và vì một boost phủ cả danh sách: **mỗi cụm từ bạn thêm vào làm yếu những cụm bạn
thật sự cần.** Xoá bất cứ thứ gì không bao giờ dùng tới.

### Model

Chọn model, số thread, phương pháp decode, blank penalty → **Apply and reload model**.
Cái này *có* load lại model nên có chờ.

- **Decoding**: chỉ `modified_beam_search` mới tôn trọng hotwords.
  `greedy_search` **âm thầm bỏ qua** chúng — hữu ích khi muốn xem baseline sạch,
  vô dụng ngoài ra.
- **Blank penalty**: đè nhẹ lên ký hiệu blank. Giúp lấy lại các phụ âm cuối bị
  ăn mất — kiểu lỗi rất đặc trưng của người Việt nói tiếng Anh. 0 là tắt.
- Model nào không bias được sẽ có nhãn `[no biasing]` ngay trong danh sách.

---

## 5. Tab Hotwords

Trên là ô soạn thảo, dưới là ô **"Handed to the decoder"**.

**Định dạng: mỗi dòng một cụm từ, không có điểm số.** Boost là con số ở tab
Control. Nếu bạn viết kiểu cũ `GUEST NETWORK :2.5`, phần `:2.5` bị **parse rồi
bỏ qua** kèm một warning — không phải lỗi, nhưng cũng không có tác dụng.

- **Apply**: dùng ngay, **không** ghi ra file.
- **Apply and save**: dùng ngay **và** ghi vào `config/hotwords.txt`.

Cả hai đều decode lại toàn bộ lịch sử.

**Cụm từ ăn từ đơn.** `GUEST NETWORK` bias tốt hơn `GUEST`, vì cây tiền tố có
nhiều ngữ cảnh hơn để cộng điểm dần.

### Ô "Handed to the decoder" — ô đáng giá nhất trên màn hình

Nó cho bạn thấy **đúng chuỗi ký tự** đã đưa vào decoder, ví dụ:

```
GUEST NETWORK/BLOCK INTERNET/BANDWIDTH LIMIT
```

Để ý dấu `/`, không phải xuống dòng: sherpa-onnx thay `/` thành `\n` trước khi
parse chuỗi hotword theo từng stream. Chữ được viết hoa hết. Cụm nào **chứa dấu
`/`** sẽ bị **bỏ** — không có cách nào escape nó.

Đây là nơi câu hỏi *"tôi sửa file rồi mà chẳng thấy gì đổi"* được trả lời. Nếu ô
này trống hoặc thiếu cụm bạn vừa thêm, vấn đề nằm trước decoder, không phải ở model.

---

## 6. Tab Rewrites

Định dạng `pattern => replacement`, áp lên **văn bản sau khi decode**.

Thứ tự thử việc, đúng thứ tự này:

1. **Thêm vào hotwords trước.** Sửa trong decoder tốt hơn hẳn: nó đổi *giả thuyết*
   chứ không vá *đầu ra*, và nó tổng quát sang các cách nói gần giống.
2. **Chỉ khi nó vẫn ra sai y như cũ hai lần** thì thêm rule ở đây.

Có những phép thay thế biasing không cứu được: nếu chữ "guest" của một người thật
sự nghe như "gas", decoder vẫn sẽ chọn "gas" dù `GUEST NETWORK` đã được boost.

Rule phải **rất hẹp**: sửa đúng một trường hợp đã quan sát được. Đừng cố làm nó
tổng quát. Cái hấp dẫn — một pass fuzzy nearest-neighbour trên cả câu — sẽ sửa
đúng trường hợp bạn đang nhìn và **âm thầm phá** những từ bạn không nhìn.

Giữ bảng không có vòng lặp: `a => b` đi cùng `b => a` sẽ đánh nhau.

Card so sánh hiện dòng `rules` cho biết rule nào đã chạy — nên rule nào không bao
giờ chạy là thấy được, và xoá được.

---

## 7. Đọc một thẻ so sánh

```
#3   mic   2.1s   rtf 0.04   WER 33% -> 0%          [ CHANGED ]
raw       TURN ON GAS NETWORK
filtered  TURN ON GUEST NETWORK
diff      turn on [gas → guest] network
rules     gas => guest
```

| dòng | nghĩa |
|---|---|
| `raw` | **Cùng model, cùng phương pháp decode, cùng audio — nhưng giữ lại danh sách hotword.** |
| `filtered` | Sau cả Stage 1 và Stage 2 |
| `diff` | Từ nào đã dịch chuyển. Phép thay thế hiện **cả hai phía** |
| `rules` | Rule Stage 2 nào đã chạy (ẩn nếu không có) |
| badge | `CHANGED` / `same` / `ERROR` |
| `rtf` | Real-time factor của lần decode có bias |
| `WER` | Chỉ hiện khi clip có transcript tham chiếu |

Dòng `raw` là lý do so sánh này *có nghĩa*. Nó không phải before/after của hai
cấu hình khác nhau ở nhiều chỗ cùng lúc — nó khác **đúng một biến**.

Lưu ý: mỗi câu được decode **hai lần** (một lần không bias, một lần có bias). Đây
là tính năng của dashboard. **Thiết bị thật chỉ chạy lần decode có bias.**

Kéo-thả file `.wav` vào cửa sổ cũng decode được, hoặc dùng nút
**Decode a WAV file…**. Ô **normalise level** chuẩn hoá âm lượng trước khi decode.

---

## 8. Khi Stage 1 bị mờ: biasing cần ba điều kiện

sherpa-onnx **không báo lỗi** khi thiếu một trong ba. Nó chỉ âm thầm không bias gì.
Vì vậy engine tự kiểm tra cả ba lúc load và nói ra cái nào thiếu:

1. **Model phải là transducer.** Whisper, Moonshine và các họ CTC không có
   hook biasing nào trong sherpa-onnx.
2. **Decoding phải là `modified_beam_search`.**
3. **Phải có `bpe.vocab`** cạnh model. Thiếu nó, đơn vị mô hình hoá duy nhất còn
   lại là `cjkchar`, thứ này cắt từ tiếng Anh thành từng chữ cái — không bao giờ
   khớp với cái decoder phát ra. Biasing suy biến thành nhiễu **mà vẫn báo thành công**.

Sửa điều 3: `bash scripts/download_models.sh --only <tên-model>`

---

## 9. Chọn model

| model | dung lượng | bias được? | ghi chú |
|---|---|---|---|
| `zipformer-small-en` | 27 MB | **có** | Mặc định. Nhạy với bias nhất |
| `zipformer-en` (medium) | 67 MB | **có** | WER tốt hơn, đề kháng bias mạnh hơn |
| `streaming-zipformer-en-2023-02-21` | 128 MB | **có** | **Vượt budget thiết bị.** Chỉ để so sánh |
| `whisper-base.en` | 153 MB | không | Baseline encoder-decoder. Xem mục 9b |
| `moonshine-tiny-en` | 42 MB | không | Baseline câu ngắn |

**Model bias được luôn là model tốt hơn cho dự án này** — đó là toàn bộ mục đích.
Các model còn lại để trả lời một câu hỏi khác: *vấn đề giọng nằm ở acoustic model
hay ở language prior?*

Vài điều cần biết:

- **Streaming zipformer** load bằng một recognizer khác (online), phải đẩy audio
  qua vòng lặp ready/decode và cần thêm một đoạn im lặng ở cuối để encoder đẩy ra
  chunk cuối. Nó chỉ thấy left-context nên WER **kém hơn** model offline cùng cỡ.
  Encoder int8 riêng nó đã 127 MB — vượt cả budget 200 MB của thiết bị. Nó ở đây
  để câu hỏi "streaming có đủ tốt không" được trả lời bằng **đo**, không bằng
  cảm giác. Registry **cố ý không bao giờ** chọn model streaming làm mặc định.
- Mặc định luôn là: bias được → int8 → **không** streaming → nhỏ nhất.
  Thứ tự sắp xếp *chính là* chính sách chọn mặc định.

---

## 9b. Whisper, và câu hỏi "dùng Initial Prompt thay biasing được không?"

**Không được, và không phải vì nó yếu — mà vì nó không tồn tại trong API.**

Whisper *bản thân model* có thể nhận prompt. Nhưng
`SherpaOnnxOfflineWhisperModelConfig` của sherpa-onnx v1.13.6 chỉ có đúng
`encoder`, `decoder`, `language`, `task`, `tail_paddings`. **Không có
`initial_prompt`, không có `prompt`.**

Điều này được xác định bằng cách **compile thử với header**, không phải bằng đọc
tài liệu — hai field đối chứng (`hotwords_file`, `tail_paddings`) compile được,
nên đúng là field bị thiếu chứ không phải phép thử sai:

```
PROBE_HOTWORDS_FILE    EXISTS
PROBE_TAIL_PADDINGS    EXISTS
PROBE_INITIAL_PROMPT   MISSING   error C2039: 'initial_prompt': is not a member of ...
PROBE_PROMPT           MISSING   error C2039: 'prompt': is not a member of ...
```

Muốn dùng thì phải **vá sherpa-onnx**. Cái đó phá đúng một quy tắc giữ cho code
này cross-compile được xuống router, nên không làm.

**Và kể cả nếu có, nó vẫn là công cụ sai cho bài toán này.** Đây là khác biệt về
bản chất:

| | Contextual biasing (đang dùng) | Initial prompt |
|---|---|---|
| Cơ chế | Cây tiền tố cộng điểm **trong beam search** | Nối text vào ngữ cảnh decoder, dịch **prior** |
| Tính chất | **Ép** — cụm từ được cộng điểm xác định | **Gợi ý** — model muốn nghe thì nghe |
| Núm điều chỉnh | Một scalar, sweep được, đo được | Không có gì để sweep |
| Phạm vi | Từng token của từng cụm từ | Cả câu, không nhắm được từ nào |
| Rủi ro riêng | Boost cao → bịa từ vựng | Whisper **nhả nguyên prompt ra transcript** |

Tên dự án là *"Ép Hotwords"*. Prompt không ép được gì.

### Số đo Whisper base.en (4 thread, int8)

| clip | whisper base.en | zipformer-small-en |
|---|---|---|
| 0.70 s | 194 ms (RTF 0.28) | 44 ms (RTF 0.06) |
| 1.50 s | 574 ms (RTF 0.38) | — |
| 3.00 s | 723 ms (RTF 0.24) | 165 ms (RTF 0.06) |
| 6.62 s | 1217 ms (RTF 0.18) | 501 ms (RTF 0.08) |
| 16.71 s | 3165 ms (RTF 0.19) | — |

Clip ngắn có chịu một khoản overhead cố định (RTF lên 0.24–0.38 khi dưới 1.5 s),
nhưng chi phí **vẫn tăng theo độ dài** — không có cái "sàn 30 giây" nào.

Ba lý do độc lập khiến nó không phải ứng viên cho router:

1. **153 MB weights** — riêng decoder int8 đã **124.6 MB**, gấp 4.6× toàn bộ
   model chính, vì vocab của Whisper có 51 864 token.
2. **2–4× thời gian decode** của zipformer.
3. **Không bias được gì cả** — mất luôn mục đích của dự án.

Nó vẫn hữu ích đúng một việc: trả lời *"giọng khó nghe là do acoustic model hay
do language prior?"*. Whisper có language prior mạnh hơn nhiều, nên nếu nó nghe
đúng chỗ zipformer nghe sai thì vấn đề nằm ở prior, không ở acoustic.

**Lưu ý khi so sánh:** Whisper ra chữ **có hoa và dấu câu**, zipformer ra **toàn
hoa**. Rule Stage 2 vẫn chạy (hai phía đều được lowercase khi load), nhưng đó là
đường yếu đã ghi rõ của phần khôi phục chữ hoa/thường.

---

## 10. Từ dashboard sang số đo

Dashboard cho bạn **cảm nhận**. Muốn có **con số** thì cần corpus giọng của
chính bạn — ngưỡng ship kèm chỉ là điểm khởi đầu, không phải câu trả lời cho
giọng của bạn.

```bat
:: 1. thu, mỗi lần một câu
build\bin\vcc_listen.exe --save-dir tests\data\clips

:: 2. gán transcript đúng vào tests\data\manifest.tsv
::    <đường-dẫn-wav>  TAB  <câu đúng>

:: 3. đo
build\bin\vcc_cli.exe --eval tests\data\manifest.tsv
```

`--eval` báo WER raw vs filtered, mức cải thiện tương đối, **số clip bị làm tệ đi**,
và bảng các phép thay thế mà bộ lọc đã sửa được / đã gây ra thêm.

Cột "clip bị làm tệ đi" là cột phải nhìn. Boost quá cao sẽ làm WER tổng thể trông
đẹp trong khi phá vài câu — và trên thiết bị thật, một câu bị phá là một lệnh sai.

Sweep boost:

```bat
for %s in (1.0 2.0 3.0 4.0) do build\bin\vcc_cli.exe --set asr.hotwords_score=%s --eval tests\data\manifest.tsv
```

Làm lại vòng sweep này **mỗi lần đổi model**.

---

## 11. Sự cố thường gặp

| Hiện tượng | Nguyên nhân |
|---|---|
| Ô Stage 1 mờ | Model không bias được — đọc dòng đỏ. Xem mục 8 |
| Sửa hotword mà không đổi gì | Xem ô "Handed to the decoder". Trống nghĩa là chưa tới decoder |
| Cụm từ biến mất khỏi ô wire | Nó chứa dấu `/`. Không escape được, hãy diễn đạt lại |
| `[not reaching the decoder]` | Stage 1 tắt, hoặc danh sách rỗng, hoặc decoding là greedy |
| Không có gì đổi ở boost 2.0 | Bình thường. Model này có thể cần cao hơn — hoặc từ đó không nhường ở mức nào cả |
| Câu bịa ra từ vựng của mình | Boost quá cao. Hạ xuống |
| "no capture devices" | Quyền micro của Windows, hoặc thiết bị đang bị app khác giữ |
| Mic vẫn bị chiếm sau khi đóng | `vcc_engine.exe` bị rớt lại. Kiểm tra Task Manager |
| Model load fail | Tab **Log** có chẩn đoán của chính sherpa-onnx |
| Từ cuối câu bị mất (model streaming) | Đã xử lý bằng đệm im lặng cuối clip. Nếu vẫn thấy, báo lại |

---

## 12. Những gì tool này **không** làm

- **Không** khớp intent, **không** điền slot, **không** thực thi lệnh. Đầu ra là
  **văn bản**. Tầng xử lý ý định là việc của nhóm khác.
- **Không** có VAD. Một clip là một câu, theo thiết kế.
- **Không** đo được giọng của bạn thay bạn. Mục 10 là việc bạn phải làm.
