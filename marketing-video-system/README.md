# Marketing Video System

URL → khảo sát sản phẩm → chọn luồng demo → xác minh → kịch bản → quay thao tác → dựng video marketing.

Đã triển khai bước 1 và 2. Hệ thống nhận URL bắt buộc; không có URL hay workflow sản phẩm mặc định. Gemini suy luận loại sản phẩm và chọn luồng từ bằng chứng của URL đó. Quay video, storyboard, TTS và dựng tự động là các bước tiếp theo.

## Chạy theo URL bất kỳ

Mở terminal tại D:\AI\Test-AI-review\marketing-video-system. Điền GOOGLE_API_KEY trong .env nếu chưa có, giữ MODEL_PROVIDER/MODEL_NAME theo tài khoản của bạn.

~~~powershell
powershell -ExecutionPolicy Bypass -File .\prepare-demo.ps1 "https://your-product.example" --max-pages 6 --max-probes 12
~~~

Thay URL mẫu bằng URL sản phẩm. demo.ps1 URL cũng chạy pipeline này với giới hạn trong configs/demo.json. File config chỉ có giới hạn trang/thao tác, không có URL cố định.

Mỗi run nằm ở artifacts/runs/prepare-demo-<id>/:

- discovery/: trang, controls, ảnh trước/sau, bằng chứng và product brief.
- plan/: selection.json, demo-plan.json, demo-plan.md với chuỗi nhiều bước.
- validation/: kết quả replay, checkpoint từng bước và screenshot.
- manifest.json: trạng thái và ready_for_recording.

Chỉ khi mọi luồng phát lại đạt checkpoint, manifest mới có ready_for_recording=true. Không đủ bằng chứng, API lỗi hoặc replay sai sẽ được ghi rõ; không dùng luồng giả để đi tiếp.

## Tái sử dụng bằng chứng đã khảo sát

~~~powershell
powershell -ExecutionPolicy Bypass -File .\discover.ps1 "https://your-product.example" --max-pages 6 --max-probes 12
powershell -ExecutionPolicy Bypass -File .\plan-demo.ps1 .\artifacts\runs\discovery-<id>\discovery.json
powershell -ExecutionPolicy Bypass -File .\validate-demo.ps1 .\artifacts\runs\demo-plan-<id>\demo-plan.json
~~~

discover hỗ trợ --visible và --offline. Offline không tạo brief Gemini nên không đủ đầu vào cho plan-demo. recheck-discovery.ps1 <discovery.json> phát lại các probe trên trang mới tải và yêu cầu Gemini viết lại brief.

## Cách workflow thay đổi theo sản phẩm

1. Playwright đọc nội dung và control thật của URL. Gemini chọn các probe có ích cho sản phẩm đó.
2. Chỉ probe đã có bằng chứng, còn được chính sách chung cho phép và có checkpoint mới đủ điều kiện chọn demo.
3. Code tạo các cặp bước liên tục: target của bước sau phải có trong kết quả bước trước, trên cùng trang.
4. Gemini chọn tối đa 3 luồng gồm 1–4 thao tác. Không áp template khóa học, cửa hàng hay dashboard.
5. Compiler từ chối ID lạ hoặc chuỗi không có bằng chứng. Có một lần sửa đề xuất bằng feedback của compiler.
6. Replay chỉ điều hướng ở đầu, thực hiện các bước liên tục và dừng ngay nếu checkpoint trung gian sai.

Ví dụ từ kiểm thử: danh mục sản phẩm → search → mở chi tiết; tài liệu → mở mục giải đáp → mở hướng dẫn; dashboard → chọn bộ lọc → xem phân tích. Đây là website mô phỏng để kiểm chứng hành vi, không phải danh sách loại website cố định trong engine. Product type là chuỗi do Gemini suy luận.

Empty state được giữ trong discovery để báo giới hạn, nhưng loại khỏi ứng viên marketing chính. Input thay đổi giá trị hoặc màn hình Loading không đủ chứng minh một chức năng. Filter chỉ xóa kết quả được kiểm tra bằng text_absent cùng các checkpoint giữ đúng trang/nội dung.

## Đăng nhập và chính sách thao tác

~~~powershell
powershell -ExecutionPolicy Bypass -File .\login.ps1 "https://your-product.example/login"
~~~

Đăng nhập thủ công, bấm nút lưu phiên; giao diện hiển thị đường dẫn rồi chờ bạn đóng. Session .auth/state.json chỉ dùng cho host được cấp trong .auth/scope.json, không được gửi sang website khác. import-session.ps1 hỗ trợ session Playwright đã có.

Các thao tác hiện được hỗ trợ: điều hướng cùng website, mở nội dung/tab/disclosure, nhập ô search và chọn filter rõ nghĩa. Chưa tự submit form, mua hàng, đăng ký khóa học, đổi dữ liệu tài khoản hoặc nộp bài. Website không có semantic rõ ràng có thể cần thêm bằng chứng hoặc tích hợp thao tác khác; hệ thống báo giới hạn tương ứng.

## Môi trường và kiểm thử

~~~powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\check.ps1 --browser
powershell -ExecutionPolicy Bypass -File .\test-llm.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
~~~

Gemini được gọi trực tiếp qua ChatGoogle của browser-use; Playwright thực thi thao tác. Browser Use Agent chưa điều khiển pipeline ở các bước này. Model không tự thay đổi khi lỗi. Planner thử lại lỗi API tạm thời tối đa 2 lần, rồi ghi thiếu phân tích nếu vẫn lỗi.

scripts/test_adaptive_gemini.py là bài smoke test tùy chọn có gọi Gemini thật để chọn workflow trên hai website mô phỏng. Bằng chứng được thu qua probe fixture; báo cáo ghi rõ phương pháp này. Server mô phỏng chỉ tồn tại trong thời gian chạy bài test.

## Cấu trúc

~~~text
src/marketing_video/
  settings.py          Cấu hình và đường dẫn
  models.py            Schema bằng chứng, workflow và checkpoint
  auth.py              Lưu/giới hạn phiên theo host
  llm.py               Gemini / Browser Use / OpenAI adapter
  discovery.py         Khảo sát và recheck
  demo_planner.py      Chọn, compile và replay workflow
  pipeline.py          Điều phối từ URL tới demo đã xác minh
  storyboard.py        Viết, compile và biên tập storyboard theo bằng chứng
  recording.py         Quay flow, animate con trỏ, kiểm tra và tách clip
  composer.py          Tạo TTS, card, phụ đề, nhạc và xuất MP4
  quality.py           Kiểm tra chuỗi nguồn, media, SRT và đóng gói ZIP
  prompts/storyboard.txt Quy tắc grounding cho nội dung marketing
  __main__.py          CLI
configs/demo.json      Giới hạn, không có URL mặc định
scripts/               Runtime và kiểm thử
artifacts/runs/        Bằng chứng và báo cáo từng lần chạy
artifacts/exports/     Video hoàn chỉnh ở bước sau
~~~

.env, .auth, .runtime, .venv và artifacts được loại khỏi Git. browser-test giữ các bản demo cũ; browser-use bên cạnh là mã nguồn upstream.

Báo cáo mới nhất được chỉ đến bởi docs/latest-discovery.json, docs/latest-demo.json và docs/latest-storyboard.json. Xem docs/architecture.md và docs/roadmap.md để theo dõi các bước còn lại.

## Task 3: tạo storyboard marketing từ demo đã xác minh

Sau khi `prepare-demo.ps1` tạo manifest có `ready_for_recording=true`, chạy:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\storyboard.ps1 ".\artifacts\runs\prepare-demo-<id>\manifest.json" -Language vi -Duration 40 -AspectRatio 16:9
~~~

Task 3 không chứa URL hoặc kịch bản cố định. Nó đọc product brief, workflow và kết quả replay từ chính manifest được truyền vào. Gemini viết hook, cảnh lợi ích, lời thoại, chỉ dẫn hình ảnh và CTA. Mỗi cảnh demo giữ `flow_id` và `step_index` để Task 4 có thể quay đúng thao tác.

Compiler chỉ chấp nhận manifest đã sẵn sàng, nguồn nằm trong cùng thư mục run, bằng chứng tồn tại, demo đủ bước đúng thứ tự và thời lượng trong ±5 giây so với mục tiêu. Nếu website có advertised claim, storyboard phải có cảnh lợi ích viện dẫn claim đó. Một lượt Gemini riêng kiểm tra claim trước khi trạng thái được đặt thành `ready`.

Mỗi run `artifacts/runs/storyboard-<id>/` có `evidence.json`, `storyboard-draft.json`, `review.json`, `storyboard.json` và `storyboard.md`.

## Task 4: quay thao tác và con trỏ

Truyền một storyboard có `status=ready` vào recorder:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\record-scenes.ps1 ".\artifacts\runs\storyboard-<id>\storyboard.json"
~~~

Thêm `-Visible` nếu muốn nhìn Chromium trong lúc quay. Recorder mở đúng URL của flow, dùng session đã giới hạn theo host, phát lại các bước liên tục và kiểm tra lại checkpoint sau mỗi thao tác. Nếu target, URL hoặc nội dung kết quả thay đổi, run được đánh dấu `failed`.

Con trỏ được render trong trang ở 1280×720, di chuyển theo easing tới tâm control và tạo vòng click trước thao tác. Với ô search, ký tự được nhập tuần tự; với select và click, thao tác vẫn đi qua chính sách read-only chung. Playwright ghi một raw WebM cho mỗi flow; FFmpeg đi kèm Playwright tách clip theo thời lượng của từng cảnh.

Mỗi run `artifacts/runs/recording-<id>/` gồm:

- `raw/`: bản quay liên tục của flow.
- `clips/`: WebM riêng cho từng cảnh demo.
- `posters/`: khung hình kết quả của mỗi cảnh.
- `screenshots/`: bằng chứng trước/sau dùng khi kiểm tra checkpoint.
- `recording-manifest.json`: nguồn, clip, trace con trỏ, mốc thời gian và kết quả checkpoint.

Các cảnh hook, benefit và CTA được liệt kê trong `narrative_scene_ids`; Task 5 sẽ dựng chúng cùng clip, lời đọc, phụ đề và nhạc.

## Task 5: TTS và dựng video hoàn chỉnh

Truyền storyboard và recording manifest tương ứng:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\compose-video.ps1 `
  ".\artifacts\runs\storyboard-<id>\storyboard.json" `
  ".\artifacts\runs\recording-<id>\recording-manifest.json"
~~~

Giọng được suy ra từ ngôn ngữ storyboard (`vi-VN-HoaiMyNeural` cho tiếng Việt), hoặc có thể chỉ định bằng `-Voice`. TTS được tạo riêng cho mỗi scene, đo duration và điều chỉnh tempo khi cần để không lệch timeline. Nếu lời đọc dài quá giới hạn an toàn, run thất bại thay vì cắt mất nội dung.

Composer tạo card cho hook/benefit/CTA từ poster sản phẩm, thêm lower-third cho cảnh demo, fade từng cảnh và chuẩn hóa toàn bộ về H.264 1280×720, 30 fps. Lời đọc được trộn với nhạc nền tạo cục bộ; video cuối dùng AAC 48 kHz stereo. File SRT UTF-8 chứa toàn bộ voiceover.

Mỗi run `artifacts/runs/video-<id>/` chứa `marketing-video.mp4`, `subtitles.srt`, `video-manifest.json`, audio riêng, segment từng cảnh, card và overlay trung gian.

## Task 6: QA và đóng gói deliverable

Chạy QA trên video manifest đã sẵn sàng:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\package-video.ps1 `
  ".\artifacts\runs\video-<id>\video-manifest.json"
~~~

Tám cổng bắt buộc kiểm tra chuỗi scene, checkpoint quay, duration, video stream, audio stream, mức âm thanh, SRT và khung hình đại diện. Chỉ khi tất cả đạt, hệ thống mới tạo thư mục và ZIP trong `artifacts/exports/`.

Gói giao khách hàng gồm MP4, SRT, contact sheet, QA report, provenance đã làm sạch, README, delivery manifest và SHA-256. `.env`, API key, `.auth`, browser session, raw state và đường dẫn tuyệt đối của máy không được đưa vào gói.
