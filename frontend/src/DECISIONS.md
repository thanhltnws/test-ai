# Design Decisions — Frontend

Ghi lại các quyết định thiết kế quan trọng, lý do chọn và những phương án đã bị loại bỏ. Mục đích: tránh lặp lại tranh luận cũ và giúp người mới hiểu tại sao code lại như vậy.

---

## Filter dùng Draft/Apply thay vì real-time

**Quyết định:** Thay đổi filter (period, market) không tự động gọi API — phải nhấn Apply.

**Lý do:** Mỗi lần thay đổi 1 dropdown (ví dụ: đổi period type từ Monthly → Quarterly) thì anchor date cũng thay đổi theo. Nếu real-time sẽ trigger 2 API calls liên tiếp. Với 3 filter cùng lúc, pattern này rất dễ gây race condition và UX giật cục.

**Phương án bị loại:** Real-time filter với debounce — phức tạp hơn và vẫn có edge case khi user thay đổi nhanh.

---

## ICP hiển thị dạng card thay vì treemap

**Quyết định:** Dùng card grid (labeled rows) thay vì treemap chart.

**Lý do:** Treemap đẹp về mặt thị giác nhưng khó đọc thông tin chi tiết — chữ bị tràn, màu sắc nhiều gây rối mắt, và không hiển thị được label (Employees / Deal size) rõ ràng. Card grid cho phép hiện đủ thông tin có context mà không cần hover.

**Lịch sử:** Đã implement treemap 2 lần (recharts Treemap và CSS flexbox thuần), cả hai đều bị loại vì UX kém. Quyết định cuối là card.

**Phương án bị loại:**
- recharts Treemap — API v3 thay đổi, content prop không render được
- CSS flexbox treemap — màu sắc quá nhiều, chữ bị chìm

---

## Chat giới hạn 6 messages history gửi lên BE

**Quyết định:** `messages.slice(-6)` — chỉ gửi 6 tin nhắn gần nhất làm history context.

**Lý do:** Cân bằng giữa context đủ dùng cho AI và token cost. 6 messages = 3 lượt hỏi-đáp — đủ để AI hiểu mạch hội thoại mà không làm prompt quá dài.

**Phương án bị loại:** Gửi toàn bộ history — token cost tăng tuyến tính, dễ hit context limit của model.

---

## Pain point tooltip hiện khi hover cả label lẫn bar

**Quyết định:** Thêm mouse event vào SVG `<text>` của YAxis custom tick, render floating tooltip `position: fixed`.

**Lý do:** Label bị truncate ở 48 ký tự (do YAxis width giới hạn). Người dùng cần hover vào label để đọc đủ nội dung và xem insight — nhưng recharts Tooltip chỉ trigger khi hover vào bar, không trigger khi hover vào label.

**Cách implement:** `labelTooltip` state `{ item, x, y }` — cập nhật theo cursor position qua `onMouseMove`. Tooltip dùng `position: fixed` để không bị clip bởi `overflow: hidden` của card.

---

## WelcomeModal không có persistence

**Quyết định:** Modal hiện mỗi lần hard refresh, không lưu "đã đọc" vào localStorage.

**Lý do:** Đây là internal demo — người xem thường là stakeholder mới, cần đọc context mỗi lần. Không phải app production nơi user cần tắt modal vĩnh viễn.
