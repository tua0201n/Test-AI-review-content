# URL → video marketing: kế hoạch triển khai

## Mục tiêu
Khách hàng cung cấp URL. Hệ thống khảo sát website, quyết định nội dung và tác vụ demo, quay thao tác thật, tạo lời thoại và dựng video quảng cáo hoàn chỉnh. Đầu ra cuối cùng là MP4, phụ đề và báo cáo bằng chứng cho các tuyên bố trong video.

## Các task và điều kiện hoàn thành

| Task | Đầu vào | Công việc | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 1. Khảo sát sản phẩm | URL | Thu thập trang, controls; AI chọn probe; thực thi và đối chiếu trước/sau | discovery.json + ảnh + product brief; phân biệt advertised / demonstrated / blocked |
| 2. Chọn luồng demo | Task 1 | AI chọn 2–3 giá trị chính và tác vụ có bằng chứng | demo-plan.json với target fingerprint và checkpoint; không chọn chức năng chưa thử được |
| 3. Viết kịch bản | Brief + demo plan | AI viết hook → vấn đề → thao tác → lợi ích → CTA | storyboard.json, lời thoại tiếng Việt, thời lượng và nguồn bằng chứng cho từng claim |
| 4. Quay các cảnh | Demo plan + storyboard | Browser Use / Playwright thực thi; con trỏ, click, gõ, scroll; kiểm tra checkpoint | clip từng cảnh, trace; hình phải cho thấy input và output thật |
| 5. Dựng tự động | Clip + lời thoại | TTS, căn thời lượng, cắt chờ, crop/zoom, ghép cảnh, phụ đề, nhạc có quyền sử dụng | video H.264/AAC + SRT; đồng bộ hình và lời nói |
| 6. Kiểm tra và đóng gói | Video | Kiểm tra claim, cảnh trống, chữ bị cắt, âm lượng; thử lại có giới hạn | MP4 hoàn chỉnh + manifest; thể hiện rõ nếu pipeline chưa hoàn tất |

Task 1 đã có triển khai v1 và kiểm thử browser. Phần gọi LLM thực tế đang bị API từ chối quyền LLM Gateway; báo cáo đánh dấu partial và analysis_status=unavailable. Tour giao diện hiện tại chưa phải kiểm thử đầy đủ sản phẩm.

## Hợp đồng dữ liệu Task 1

- PageEvidence: URL, nội dung, controls và ảnh.
- ProbeRequest: control ID từ DOM thật, thao tác, giá trị đầu vào và điều cần quan sát.
- ProbeEvidence: ảnh trước/sau, target_fingerprint để tìm lại control, trạng thái và thay đổi quan sát được.
- ProductBrief: định vị, giả thuyết khách hàng, tính năng quảng bá có page ID nguồn, probe ID có thể demo và giới hạn.
- DiscoveryReport schema_version=1.0: trạng thái tổng thể và analysis_status riêng cho LLM.

Trạng thái demonstrated nghĩa là thao tác tạo thay đổi ở URL, nội dung, tab hoặc disclosure; chưa xác nhận toàn bộ nghiệp vụ backend. Nhập query mà không có kết quả UI thay đổi nhận no_observable_result. Nội dung quảng bá dashboard không chứng minh dashboard thật đã hoạt động. Task 2 phải thêm checkpoint cụ thể trước khi đưa tác vụ vào quảng cáo.

## Chạy Task 1

Trong browser-test:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\discover.ps1 https://aisoeasy.co/
~~~

URL là đầu vào bắt buộc duy nhất. Model và API key là cấu hình hệ thống trong .env, không phải thông tin khách hàng phải điền cho từng video. Giữ nguyên model đã cấu hình.

Tùy chọn phát triển:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\discover.ps1 https://aisoeasy.co/ --max-pages 8 --max-probes 10
powershell -ExecutionPolicy Bypass -File .\discover.ps1 https://aisoeasy.co/ --offline
.\.venv-test\Scripts\python.exe -m unittest discover -s tests -v
~~~

Báo cáo: results/discovery-*/discovery.json và discovery.md. Ảnh trước/sau: screenshots/. Kế hoạch từng trang: page-*-plan.json.

Exit code: 0 = hoàn tất chế độ đã chọn; 1 = có phần chưa hoàn tất; 2 = thất bại. Khi LLM lỗi, ngừng gọi API thất bại lặp lại, tiếp tục khảo sát heuristic và đánh dấu analysis_status=unavailable. Chế độ offline không sinh product brief bằng AI.

## Giới hạn và hướng triển khai

- URL chỉ cho phép trải nghiệm chức năng công khai. Với tính năng yêu cầu đăng nhập, cần tài khoản demo/phiên được cấp hoặc chế độ demo công khai. Không suy ra nội dung bên trong từ landing page.
- Task 1 dùng Playwright cho thao tác và wrapper LLM của Browser Use cho kế hoạch/brief. Chưa dùng Browser Use Agent để điều khiển khảo sát. Task 4 có thể dùng Agent cho tác vụ thích ứng và Playwright cho luồng tái lập.
- Giới hạn số trang/probe; chưa xử lý control trong iframe, canvas và shadow DOM sâu.
- Heuristic fallback chỉ thử search/disclosure/tab; không thay LLM quyết định nội dung marketing.
- Thay đổi UI không đủ chứng minh kết quả tìm kiếm đúng. Task 2 cần checkpoint theo ngữ nghĩa.
- public_review.py là demo riêng theo website mẫu, chưa phải pipeline URL-to-video tổng quát.

## Kiểm thử

1. Search có kết quả thay đổi → demonstrated.
2. Input có thể nhập nhưng kết quả không đổi → no_observable_result.
3. Disclosure đổi trạng thái → demonstrated.
4. Form mua hàng và link thay đổi dữ liệu không được thực thi.
5. Brief tham chiếu probe không tồn tại/chưa demonstrated bị từ chối.
6. LLM lỗi: giữ bằng chứng browser, không báo AI đã phân tích thành công.

## Kết quả khảo sát đầu tiên

Website aisoeasy.co: đã thu thập 5 trang, ghi nhận menu ngôn ngữ có thay đổi quan sát được, ô tìm kiếm việc làm nhận query nhưng kết quả không đổi, các trang đăng nhập/đăng ký được đánh dấu cần phiên truy cập. Không coi các chức năng học, chứng nhận và dashboard được quảng bá là đã kiểm thử.

Báo cáo thực tế: [discovery.md](results/discovery-20261013-161504-051588/discovery.md).

API trả lỗi tài khoản chưa được phép dùng LLM Gateway. Chưa sinh product brief bằng AI. Có thể cấu hình một provider có quyền API trong .env hoặc dùng chế độ offline để tiếp tục kiểm tra browser; hệ thống không tự thay model.

Tài liệu API đã đối chiếu: [Supported Models](https://docs.browser-use.com/open-source/supported-models), [Output Format](https://docs.browser-use.com/open-source/customize/agent/output-format).
