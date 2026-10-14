# Browser Use model test

Thư mục ../browser-use là mã nguồn thư viện. Dự án này chạy phiên bản browser-use 0.13.11 theo uv.lock, không tự động sử dụng checkout bên cạnh.

## Chạy trên Windows PowerShell

1. Mở .env và điền BROWSER_USE_API_KEY cho ChatBrowserUse. MODEL_NAME để trống sẽ dùng mặc định của phiên bản đang cài.
2. Chạy các lệnh bên dưới trong thư mục browser-test:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\run.ps1 --check
powershell -ExecutionPolicy Bypass -File .\run.ps1 --smoke
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Test mặc định khám phá aisoeasy.co, thử các chức năng công khai và ghi hình MP4. Giới hạn 35 bước. Để test tác vụ khác:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 --task "Open https://aisoeasy.co/ and report the heading" --max-steps 5 --headless
```

Kết quả mỗi lần gọi model được lưu trong results/run-*.json. Lệnh --check và --smoke không gọi model. API key có thể cần tài khoản có credit.

## Model khác / API tương thích OpenAI

Điền trong .env:

```dotenv
MODEL_PROVIDER=openai
MODEL_NAME=ten-model-cua-ban
OPENAI_API_KEY=
OPENAI_BASE_URL=
```

OPENAI_BASE_URL có thể để trống với OpenAI hoặc đặt endpoint tương thích của nhà cung cấp. Model cần hỗ trợ structured output và khả năng phù hợp với Browser Use; không phải mọi endpoint tương thích đều đáp ứng.

## Môi trường

Môi trường .venv cũ trỏ tới Python đã mất. Các script dùng .venv-test, Python và cache cục bộ .uv-python / .uv-cache, Chromium tại .browsers. Dùng run.ps1 để tự thiết lập các biến môi trường này trước khi chạy uv.

.env được bỏ qua bởi Git. Không đưa API key vào mã nguồn.

Tài liệu: https://docs.browser-use.com/open-source/quickstart

Model được cấu hình theo ../browser-use/examples/simple.py: bu-2-0-mini-preview.

Kiểm tra môi trường hiện tại: Chromium/Playwright khởi động thành công, nhưng Browser Use CDP trả lỗi "did not receive a valid HTTP response". Chạy --smoke trong terminal của bạn để kiểm tra lại kết nối này. Chưa chạy gọi model do chưa có BROWSER_USE_API_KEY.

## Video review marketing

Quay tour công khai khoảng 90 giây, có chú thích tiếng Việt, không cần API key:

```powershell
powershell -ExecutionPolicy Bypass -File .\review-video.ps1
```

Luồng quay: trang chủ → Product → Learning Paths → Individuals → Jobs và tìm kiếm Marketing → Pricing → Signup → Login → trang chủ. Không gửi form hay tạo tài khoản. Video có chú thích, chưa lồng tiếng hoặc nhạc. Lời thoại để thu âm nằm trong voiceover-vi.txt. Các cảnh sản phẩm/lộ trình là nội dung giới thiệu trên trang công khai, không xác nhận chức năng trong tài khoản đã hoạt động.

Đầu ra: results/public-review-*/review-marketing.mp4, voiceover-vi.txt, observations.json và screenshot từng cảnh. Có thể thêm --visible để xem trình duyệt khi quay.

Chạy agent bằng model (cần API key):

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 --max-steps 35
```

Agent mặc định ghi MP4 ở results/review-*/video/ và báo cáo, kịch bản review ở review-script.txt. Thêm --no-video để tắt ghi hình. Đây là bản ghi thao tác thực tế; thời lượng phụ thuộc số bước và không tự lồng tiếng/cắt dựng theo 90 giây. Phần chức năng yêu cầu tài khoản có thể kiểm tra sau bước --login bên dưới.

### Trải nghiệm sau đăng nhập

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 --login
powershell -ExecutionPolicy Bypass -File .\run.ps1 --max-steps 50
```

Lệnh --login mở trình duyệt riêng, bạn đăng nhập rồi nhấn Enter trong terminal để lưu phiên tại .auth/state.json. Không quay bước đăng nhập. Lệnh chạy agent tiếp theo tự tải phiên này; không gửi form hoặc thay đổi dữ liệu mặc định. Phiên dựa trên cookies/localStorage; nếu website dùng cơ chế khác hoặc phiên hết hạn có thể cần đăng nhập lại. File phiên có dữ liệu đăng nhập, đã được bỏ qua bởi Git.

### Con trỏ và animation trong video demo

Lệnh review-video.ps1 hiện quay con trỏ chuột dạng mũi tên trắng, di chuyển theo quỹ đạo mượt, hiệu ứng thu nhỏ khi nhấn và vòng tròn lan ra tại vị trí click. Các lần click dùng sự kiện chuột thật để kích hoạt nút/link; tiêu đề và nhãn thông tin được hover để giới thiệu. Tìm kiếm việc làm được gõ từng ký tự. Chú thích vào cảnh có hiệu ứng fade/slide.

Video mặc định được điều chỉnh tốc độ để tối đa khoảng 90 giây. Thêm --pace 1.5 để tăng thời gian đọc và độ dài tối đa khoảng 135 giây. Log click/hover nằm ở actions.json cạnh video. Hiệu ứng này áp dụng cho tour công khai review-video.ps1.

## Dự án URL → video marketing

Kế hoạch từng task: [PROJECT_PLAN.md](PROJECT_PLAN.md).

Task 1 nhận URL bất kỳ, khảo sát chức năng và lưu bằng chứng. Chạy discover.ps1 với URL làm đối số. Kết quả nằm trong results/discovery-*/discovery.md và discovery.json. public_review.py trước đó là demo riêng, chưa phải pipeline tổng quát.
