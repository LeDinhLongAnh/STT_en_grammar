# Global Prompt versions

## V2 strong — preserved baseline

V2 used a dense 209/223-token phrase bank. It was reliable because it:

- named every router intent, entity family, application, and bandwidth value;
- used exact command-shaped phrases instead of prose instructions;
- kept difficult contrasts such as `block` / `unblock` in the prompt;
- repeated `Guest Wi-Fi` and `Unblock internet` near the end as high-risk anchors.

V2 prompt:

> Home router commands. Network status. Check network. Network condition. Connection quality. Speed test. Router status. Check router. Router information. Wi-Fi device info. Device information and details. Phone, tablet, laptop, smart TV, PlayStation. Online devices. Connected devices. Number of devices online. Who is online. Gaming sessions. Playing games. Who is gaming. Guest Wi-Fi. Guest network. Turn on guest Wi-Fi. Turn off guest Wi-Fi. Enable or disable guest Wi-Fi. Open QoS. Device activity. Gaming or video streaming. Bandwidth limit. Speed limit. Set limit to ten, twenty, fifty, one hundred. Block internet. Disable internet. Cut off internet access. Unblock internet. Restore internet access. Remove internet block. Block YouTube, Facebook, TikTok, Netflix, Instagram. Unblock YouTube, Facebook, TikTok, Netflix, Instagram. My son, mom, dad, Alice, John. Guest Wi-Fi. Unblock internet. Unblock application.

Measured on the 20-file clean synthetic corpus: WER 0%. In a direct interleaved
A/B run, mean RTF was 0.966.

## V3 lean — current default

V3 compresses equivalent concepts into coordinated phrases and keeps only the
anchors that fixed observed failures. It uses 124/223 tokens.

V3 prompt:

> Home router commands. Network status, condition, connection quality, speed test. Router status, information. Wi-Fi device info: son, mom, dad, Alice, John; phone, tablet, laptop, TV, PlayStation. Online and connected devices, number online. Gaming sessions. Guest Wi-Fi on or off, enable or disable. Open QoS, device activity, streaming. Bandwidth or speed limit: ten, twenty, fifty, one hundred. Block internet or applications. Unblock internet or applications. YouTube, Facebook, TikTok, Netflix, Instagram. Guest Wi-Fi. Unblock internet.

Direct interleaved A/B on the same 20 files and model process:

| Prompt | Tokens | WER | Mean RTF |
|---|---:|---:|---:|
| V2 strong | 209 | 0.00% | 0.966 |
| V3 lean | 124 | 0.00% | 0.772 |

V3 was about 20% faster in this run while preserving the same clean-corpus WER.
On 12 selected real-mic hard cases, V3 plus the closed-domain resolver routed
12/12 to the expected scenario. The adaptive scenario re-decode still handles
phonetic failures such as `guest Wi-Fi` becoming `rest weapon` or `S2 file`.

These measurements are local baselines, not a guarantee for unseen speakers or
noise. Keep V2 as the rollback reference and expand the real-mic corpus before
changing V3 anchors.
