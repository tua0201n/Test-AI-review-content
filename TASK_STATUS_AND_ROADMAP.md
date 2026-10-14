# Tổng hợp công việc và định hướng phát triển

> Cập nhật ngày: 14/10/2026  
> Phạm vi rà soát: toàn bộ repository `Test-AI-review`, lịch sử Git, mã nguồn, kiểm thử, tài liệu roadmap và các artifact gần nhất.

## 1. Tóm tắt trạng thái

Hệ thống chính `marketing-video-system` đã triển khai đủ pipeline từ URL đến gói video marketing có thể bàn giao:

`URL → khảo sát → chọn và xác minh demo → storyboard → quay → TTS/dựng video → QA/đóng gói`

Lần chạy gần nhất cho **AI So Easy — Workforce Upskill Platform** đã tạo video 37 giây, 1280×720, 30 fps, có giọng đọc tiếng Việt, nhạc, phụ đề và gói ZIP. Kết quả QA đạt **8/8 cổng chất lượng**, không phát hiện file nhạy cảm trong gói và không có checksum sai lệch.

Trước khi tạo báo cáo này, repository không có thay đổi chưa commit theo `git status`. Nhánh `main` có hai commit; phần lớn hệ thống được đưa vào commit `3ff61c0` (`settup for project`).

## 2. Các task đã hoàn thành

### 2.1. Nền tảng và prototype ban đầu

- [x] Thêm mã nguồn upstream `browser-use` dưới dạng submodule/phụ thuộc tham chiếu.
- [x] Tạo prototype `browser-test` để kiểm tra Browser Use, Playwright và luồng review website.
- [x] Có script cài đặt, kiểm tra môi trường, smoke test, chạy agent và lưu kết quả theo từng run.
- [x] Có tour review công khai không cần API key, quay MP4, lưu ảnh từng cảnh, log thao tác và lời thoại tiếng Việt.
- [x] Có cơ chế đăng nhập thủ công rồi lưu phiên cục bộ; dữ liệu phiên và API key được loại khỏi Git.
- [x] Triển khai discovery v1 nhận URL tùy ý, lưu bằng chứng trước/sau và giữ bằng chứng browser khi LLM lỗi.
- [x] Có chính sách read-only: không gửi form, mua hàng hoặc thay đổi dữ liệu ngoài ý muốn.
- [x] Có kiểm thử cho discovery, bằng chứng, LLM failure và chính sách an toàn.

`browser-test` hiện được xem là prototype/lịch sử thử nghiệm; pipeline được phát triển đầy đủ nằm trong `marketing-video-system`.

### 2.2. Task 1 — Khảo sát website và chức năng

- [x] Nhận URL bắt buộc, không khóa cứng website hoặc loại sản phẩm.
- [x] Crawl có giới hạn bằng Playwright; thu thập trang, nội dung và control thực tế.
- [x] Dùng Gemini chọn probe phù hợp, sau đó thực thi và lưu ảnh trước/sau.
- [x] Phân biệt nội dung được quảng bá, chức năng đã chứng minh, thao tác không có kết quả và phần bị chặn.
- [x] Tạo `discovery.json`, báo cáo dễ đọc và product brief bám nguồn.
- [x] Hỗ trợ khảo sát có phiên đăng nhập được giới hạn theo host.
- [x] Khi API lỗi, dừng retry có giới hạn, không bịa kết quả và vẫn bảo toàn bằng chứng đã thu thập.

Bằng chứng gần nhất: 7 trang, 12 probe, trạng thái `complete`; 21 kiểm thử được ghi nhận đạt.

### 2.3. Task 2 — Chọn và xác minh luồng demo

- [x] Tạo đồ thị thao tác liên tục từ bằng chứng discovery.
- [x] Gemini suy luận loại sản phẩm và chọn tối đa 3 workflow có giá trị marketing.
- [x] Compiler từ chối ID lạ, hành động chưa chứng minh và chuỗi bước không liên tục.
- [x] Hỗ trợ luồng 1–4 bước, checkpoint theo từng bước và checkpoint cuối.
- [x] Replay thao tác thực tế; dừng ngay nếu bước trung gian thất bại.
- [x] Chỉ đặt `ready_for_recording=true` khi toàn bộ workflow vượt qua xác minh.
- [x] Đã kiểm chứng khả năng thích ứng trên nhiều loại sản phẩm mô phỏng và với Gemini thật.

Bằng chứng gần nhất: plan, validation và manifest đều tồn tại; trạng thái `ready`; 28 kiểm thử được ghi nhận đạt.

### 2.4. Task 3 — Viết storyboard marketing

- [x] Sinh storyboard từ manifest Task 2 đã xác minh, không dùng kịch bản cố định.
- [x] Tạo hook, lợi ích, cảnh demo, lời thoại và CTA theo ngôn ngữ/thời lượng/tỷ lệ khung hình yêu cầu.
- [x] Gắn mỗi claim và cảnh demo với evidence ID tương ứng.
- [x] Compiler kiểm tra nguồn, thứ tự đầy đủ của workflow và sai số thời lượng.
- [x] Có vòng biên tập độc lập bằng Gemini; storyboard không đạt được đánh dấu `needs_revision`.

Bằng chứng gần nhất: storyboard `ready`, 5 cảnh, 37 giây, model `gemini-3.5-flash-lite`; 34 kiểm thử được ghi nhận đạt.

### 2.5. Task 4 — Quay các cảnh chức năng

- [x] Quay theo đúng storyboard và workflow đã xác minh.
- [x] Tái tìm control bằng fingerprint, nạp session đúng host và kiểm tra checkpoint sau mỗi thao tác.
- [x] Ghi raw WebM liên tục để giữ trạng thái giữa các bước.
- [x] Render con trỏ có easing, click pulse và hiệu ứng gõ từng ký tự.
- [x] Tách clip theo cảnh bằng FFmpeg; lưu poster, screenshot và trace thao tác.
- [x] Từ chối storyboard chưa được duyệt hoặc run có checkpoint thất bại.

Bằng chứng gần nhất: recording `ready`, 2 cảnh demo, 4 checkpoint đạt, 1280×720; 36 kiểm thử được ghi nhận đạt.

### 2.6. Task 5 — TTS và dựng video tự động

- [x] Tạo TTS riêng cho từng cảnh, đo thời lượng và điều chỉnh tempo an toàn.
- [x] Tạo card cho hook/lợi ích/CTA và lower-third cho cảnh demo.
- [x] Chuẩn hóa video H.264 1280×720, 30 fps.
- [x] Ghép giọng đọc, nhạc nền, hiệu ứng chuyển cảnh và audio AAC 48 kHz stereo.
- [x] Sinh phụ đề SRT UTF-8 khớp toàn bộ voiceover.
- [x] Thất bại rõ ràng khi asset thiếu, nguồn không khớp hoặc lời đọc vượt giới hạn.

Bằng chứng gần nhất: video `ready`, 37 giây, giọng `vi-VN-HoaiMyNeural`; 38 kiểm thử được ghi nhận đạt.

### 2.7. Task 6 — QA và đóng gói bàn giao

- [x] Kiểm tra chuỗi scene, bằng chứng quay, thời lượng, video stream, audio stream, âm lượng, phụ đề và mẫu hình ảnh.
- [x] Tạo contact sheet và báo cáo QA.
- [x] Đóng gói theo whitelist, không sao chép toàn bộ thư mục run.
- [x] Loại `.env`, API key, session, raw browser state và đường dẫn máy khỏi deliverable.
- [x] Tạo provenance sạch, SHA-256, thư mục bàn giao và ZIP.

Kết quả gần nhất:

- 8/8 quality gate đạt.
- Video: H.264, 1280×720, 30 fps.
- Audio: AAC, 48 kHz stereo; trung bình -22.5 dB, peak -5.1 dB.
- 5/5 block phụ đề đúng thứ tự và khớp lời thoại.
- 0 forbidden hit và 0 checksum mismatch.
- Archive SHA-256: `bfd68faf4a04703c0bd4b8551bc2f32c91bcc368db8748b998cd6d7986284cdc`.
- 40 kiểm thử được manifest bàn giao ghi nhận đạt.

### 2.8. Tài liệu, cấu hình và kiểm thử

- [x] Có README, kiến trúc, roadmap và con trỏ JSON tới artifact mới nhất.
- [x] Có CLI và script PowerShell riêng cho setup, check, discovery, planning, validation, storyboard, recording, composing và packaging.
- [x] Khóa phiên bản dependency bằng `uv.lock`.
- [x] Có schema Pydantic cho các hợp đồng dữ liệu giữa các bước.
- [x] Có kiểm thử cho discovery, auth, planner, workflow thích ứng, Gemini adapter, storyboard, recording, composer, QA và lỗi lưu file.
- [x] Các đường dẫn artifact được tham chiếu trong `docs/latest-*.json` đã được kiểm tra và hiện đều tồn tại.

## 3. Điểm tồn tại đã phát hiện

- Phần mở đầu `marketing-video-system/README.md` vẫn ghi mới hoàn thành Task 1–2 và coi Task 3–5 là bước tiếp theo. Thông tin này không còn khớp với roadmap, mã nguồn và artifact thực tế.
- `docs/latest-discovery.json` và một số file `latest-*.json` vẫn chứa trường `next_task` của thời điểm trung gian. Nên cập nhật để tránh người đọc hiểu đó là trạng thái hiện tại của toàn dự án.
- `browser-test/README.md` ghi nhận lỗi Browser Use CDP trong môi trường prototype và chưa gọi model vì thiếu API key ở lần thử đó. Đây là trạng thái lịch sử của prototype, không phải kết quả QA cuối của hệ thống chính.
- Lần chạy test lại trong đợt rà soát này đã khởi động được các bài test tích hợp nhưng không trả về dòng tổng kết trong phiên công cụ. Vì vậy tài liệu này dùng số test từ manifest/artifact đã lưu, không tuyên bố có một lượt regression mới hoàn tất trong lúc lập báo cáo.
- Repository mới có lịch sử commit rất ngắn; chưa thấy cấu hình CI tự động trong phạm vi rà soát.

## 4. Định hướng task tiếp theo

### P0 — Nên thực hiện ngay

- [ ] **Đồng bộ tài liệu trạng thái:** sửa phần mở đầu README và các trường `next_task` cũ để phản ánh pipeline đã hoàn thành đủ 6 bước.
- [ ] **Tạo một lệnh end-to-end:** thêm command/script nhận URL và chạy tuần tự discovery → plan/validate → storyboard → record → compose → QA/package, có resume từ bước lỗi.
- [ ] **Thiết lập CI:** chạy unit/integration test, lint/type-check và kiểm tra schema trên mỗi pull request; lưu log và artifact khi thất bại.
- [ ] **Chạy regression sạch:** thiết lập lại môi trường rồi chạy toàn bộ test đến khi có exit code và báo cáo tổng kết rõ ràng; cập nhật số liệu test theo lần chạy mới.
- [ ] **Chuẩn hóa version/release:** sửa typo commit ban đầu nếu cần ở tài liệu, thêm changelog, version cho pipeline và quy ước migration schema.

### P1 — Tăng độ tin cậy để dùng thực tế

- [ ] **Kiểm thử nhiều website thật hơn:** lập bộ benchmark đa dạng gồm SaaS, e-commerce, tài liệu, dashboard, LMS và website đa ngôn ngữ; đo tỷ lệ hoàn thành từng bước.
- [ ] **Cải thiện đăng nhập:** hướng dẫn rõ vòng đời session, phát hiện session hết hạn, hỗ trợ refresh/re-login và vẫn giới hạn đúng host.
- [ ] **Mở rộng control được hỗ trợ:** iframe, shadow DOM, canvas, virtualized list, autocomplete phức tạp và SPA có loading dài.
- [ ] **Tăng độ bền target fingerprint:** thêm chiến lược fallback khi DOM thay đổi nhưng semantic vẫn giữ nguyên; chấm điểm độ tin cậy trước khi thao tác.
- [ ] **Bổ sung retry có kiểm soát:** phân loại lỗi browser/network/model/media, retry theo bước và tránh chạy lại các bước đã có artifact hợp lệ.
- [ ] **Tăng kiểm tra nội dung:** phát hiện claim quá mạnh, nội dung nhạy cảm, dữ liệu cá nhân và sai khác giữa lời thoại, phụ đề, hình ảnh.

### P2 — Nâng chất lượng video và khả năng sản phẩm hóa

- [ ] **Template thương hiệu:** màu sắc, font, logo, intro/outro, CTA và safe area theo từng khách hàng.
- [ ] **Nâng chất lượng dựng:** smart crop/zoom, loại khoảng chờ, cân loudness theo chuẩn, ducking nhạc và nhiều tỷ lệ 16:9, 9:16, 1:1.
- [ ] **Cho phép duyệt thủ công:** UI hoặc report để người dùng duyệt/chỉnh workflow, storyboard và claim trước khi tốn chi phí quay/dựng.
- [ ] **Quan sát vận hành:** dashboard cho thời gian, chi phí token/TTS, tỷ lệ thành công, lỗi theo bước và provenance của mỗi run.
- [ ] **Quản lý artifact:** retention policy, dọn run cũ an toàn, cache theo fingerprint đầu vào và lưu trữ ngoài máy khi cần.
- [ ] **Đóng gói triển khai:** container/worker queue, giới hạn concurrency, timeout, quota và cơ chế hủy job.

### P3 — Mở rộng dài hạn

- [ ] Hỗ trợ nhiều provider LLM/TTS với kiểm thử tương thích và fallback được cấu hình rõ ràng.
- [ ] Sinh nhiều biến thể video/A-B test từ cùng một bộ bằng chứng.
- [ ] Thêm đánh giá tự động về brand compliance, accessibility và chất lượng marketing.
- [ ] Xây dựng API/service và giao diện quản lý job cho người dùng không làm kỹ thuật.
- [ ] Theo dõi thay đổi website và tự xác định lúc nào cần khảo sát/quay lại.

## 5. Thứ tự triển khai đề xuất

1. Đồng bộ README và metadata trạng thái.
2. Chạy regression sạch và đưa test vào CI.
3. Tạo command end-to-end có resume/idempotency.
4. Xây bộ benchmark website thật và đo baseline.
5. Cải thiện session, target fingerprint và các control phức tạp dựa trên lỗi benchmark.
6. Thêm bước duyệt thủ công và template thương hiệu.
7. Sau khi tỷ lệ thành công ổn định, đóng gói thành service có queue, observability và quản lý artifact.

## 6. Tiêu chí hoàn thành cho milestone tiếp theo

Milestone tiếp theo có thể xem là hoàn thành khi:

- Một lệnh duy nhất tạo được deliverable từ URL hoặc tiếp tục an toàn từ run dang dở.
- CI chạy ổn định và xuất báo cáo đầy đủ cho toàn bộ test.
- README, roadmap và `latest-*.json` thống nhất trạng thái.
- Bộ benchmark có ít nhất 5 nhóm website và công bố tỷ lệ thành công theo từng bước.
- Không thao tác ghi dữ liệu nếu chưa được cấp quyền rõ ràng.
- Mọi video bàn giao vẫn phải vượt 8 cổng QA, security scan và checksum validation.

## 7. Nguồn dùng để xác nhận trạng thái

- `marketing-video-system/docs/roadmap.md`
- `marketing-video-system/docs/architecture.md`
- `marketing-video-system/docs/latest-discovery.json`
- `marketing-video-system/docs/latest-demo.json`
- `marketing-video-system/docs/latest-storyboard.json`
- `marketing-video-system/docs/latest-recording.json`
- `marketing-video-system/docs/latest-video.json`
- `marketing-video-system/docs/latest-delivery.json`
- `marketing-video-system/artifacts/runs/qa-20261014-033208-937260/qa-report.md`
- `marketing-video-system/artifacts/runs/qa-20261014-033208-937260/delivery-manifest.json`
- Các module trong `marketing-video-system/src/marketing_video/` và các test trong `marketing-video-system/tests/`.
- `browser-test/README.md`, `browser-test/PROJECT_PLAN.md` và `browser-test/tests/`.
- Lịch sử Git và trạng thái working tree tại thời điểm rà soát.
