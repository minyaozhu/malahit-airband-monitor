// On-device speech-to-text for a WAV file via macOS Speech framework.
// Built into Transcribe.app (needs a bundle for the permission prompt).
// Usage: open -W -n Transcribe.app --args <audio.wav> <out.txt> [locale, default en-US]
import Foundation
import Speech

let args = CommandLine.arguments
guard args.count >= 3 else { fputs("usage: transcribe <audio> <out.txt>\n", stderr); exit(2) }
let audio = URL(fileURLWithPath: args[1]), out = URL(fileURLWithPath: args[2])
let locale = args.count > 3 ? args[3] : "en-US"

func finish(_ text: String, _ code: Int32) -> Never {
    try? text.write(to: out, atomically: true, encoding: .utf8)
    exit(code)
}

SFSpeechRecognizer.requestAuthorization { status in
    guard status == .authorized else { finish("ERROR: speech recognition not authorized (\(status.rawValue))", 3) }
    guard let rec = SFSpeechRecognizer(locale: Locale(identifier: locale)), rec.isAvailable else {
        finish("ERROR: \(locale) recognizer unavailable", 4)
    }
    guard rec.supportsOnDeviceRecognition else { finish("ERROR: on-device recognition not supported for \(locale)", 5) }
    let req = SFSpeechURLRecognitionRequest(url: audio)
    req.requiresOnDeviceRecognition = true   // never send audio to Apple
    req.shouldReportPartialResults = false
    req.addsPunctuation = true
    rec.recognitionTask(with: req) { result, error in
        if let r = result, r.isFinal {
            let segs = r.bestTranscription.segments
            let conf = segs.isEmpty ? 0 : segs.map(\.confidence).reduce(0, +) / Float(segs.count)
            finish("\(r.bestTranscription.formattedString)\n---\nsegments=\(segs.count) mean_confidence=\(String(format: "%.2f", conf))", 0)
        }
        if let e = error { finish("ERROR: \(e.localizedDescription)", 6) }
    }
}
DispatchQueue.main.asyncAfter(deadline: .now() + 120) { finish("ERROR: timed out", 7) }
RunLoop.main.run()
