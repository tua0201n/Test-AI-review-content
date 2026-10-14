# Roadmap

| Task | Trạng thái | Đầu ra |
|---|---|---|
| 1. Khảo sát website và chức năng | Đã hoàn thành khảo sát có giới hạn sau đăng nhập, brief Gemini và bằng chứng trước/sau; xem docs/latest-discovery.json | discovery.json, product brief, ảnh trước/sau |
| 2. Chọn tác vụ và luồng demo | Đã hoàn thành workflow thích ứng theo URL, replay từng bước; 28 kiểm thử đạt, pipeline tích hợp thực tế ready_for_recording và Gemini thật kiểm chứng trên hai sản phẩm mô phỏng | demo-plan.json với target fingerprint và checkpoint |
| 3. Kịch bản marketing | Đã hoàn thành storyboard tổng quát theo manifest Task 2, kiểm tra grounding hai lớp và chạy Gemini thật; xem docs/latest-storyboard.json | storyboard.json, hook, lợi ích, lời thoại, CTA, editorial review |
| 4. Quay các cảnh chức năng | Đã hoàn thành recorder tổng quát theo storyboard: raw flow, clip từng cảnh, con trỏ easing/click pulse, poster và checkpoint trace; xem docs/latest-recording.json | clips WebM, cursor animation, poster, trace thao tác |
| 5. Dựng tự động và TTS | Đã hoàn thành composer tổng quát: TTS theo scene, card narrative, lower-third, SRT, nhạc nền, H.264/AAC MP4; xem docs/latest-video.json | MP4, SRT, lời thoại và nhạc |
| 6. QA và đóng gói | Đã hoàn thành 8 cổng chất lượng, contact sheet, provenance sạch, SHA-256 và ZIP giao khách hàng; xem docs/latest-delivery.json | video hoàn chỉnh + manifest chất lượng + ZIP |

Một URL là đầu vào cho mỗi sản phẩm. Provider/model/API key là cấu hình của hệ thống. Task 2 chỉ chọn những chức năng có bằng chứng; các tuyên bố quảng cáo phải gắn với nguồn. Với chức năng sau đăng nhập, cần phiên demo được cấp hoặc chế độ demo công khai.
