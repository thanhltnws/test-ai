# Phạm vi và kỳ vọng

> Những điểm dễ bị hiểu sai nếu không được làm rõ — về những gì hệ thống làm được, không làm được, và tại sao thiết kế lại như vậy.

## Vai trò của AI trong hệ thống

AI trong hệ thống này đóng vai trò **processor** — đọc, hiểu, và tổng hợp data sau khi data đã được tập trung về một chỗ. Không phải **collector**.

Một kỳ vọng phổ biến là AI sẽ tự động crawl data từ mọi nền tảng đang dùng. Trên thực tế điều này bất khả thi với nhiều nguồn quan trọng: GA4 không expose raw event data cho third-party, Jira của khách nằm trong tenant riêng, feedback Sales nằm trong chat nội bộ. Với những nguồn này, cần **operation change song song** — người có trách nhiệm chủ động ghi lại thông tin vào tool nội bộ.

Đây không phải hạn chế của thiết kế mà là đặc điểm của bài toán: những vấn đề phát sinh trong quá trình triển khai dự án — mà đội Ops trực tiếp quan sát — là nguồn bổ sung pain point, ICP và use case thực tế cho Marketing và Sales. Nguồn data này không tồn tại ở bất kỳ platform nào; nó chỉ tồn tại nếu có quy trình để capture nó.
