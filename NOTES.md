# Ghi chú phân tích · Day 04

Họ và tên: Nguyen Duc Thang
MSSV: 2A202603798

## 1. Case được chọn

- ID case: E5
- Câu trả lời của agent:
  "Hiện tại, dịch vụ Copilot Mission Control trên GitHub không ghi nhận sự cố nào đang diễn ra, với trạng thái \"All Systems Operational\". Tuy nhiên, có một sự cố gần đây đã xảy ra với tên là \"Increased task-related errors for Copilot Mission Control\", đã được giải quyết vào ngày 4 tháng 11 năm 2026.

  Về câu hỏi của bạn, nếu trường components rỗng, điều này không thể kết luận rằng không có dịch vụ bị ảnh hưởng. Điều này chỉ có nghĩa là không có thành phần cụ thể nào được chỉ định trong danh sách sự cố. Mặc dù không ghi nhận thành phần nào bị ảnh hưởng, sự cố vẫn có thể xảy ra và ảnh hưởng đến dịch vụ. 

  Thông tin chi tiết về tình trạng hiện tại có thể tham khảo từ [GitHub Status](https://www.githubstatus.com)."
- Điểm ở lần chạy 1: 55/100 (Factuality: 15/40, Completeness: 20/25, Evidence: 15/20, Boundaries: 5/15)

## 2. Bằng chứng trong trace

Dán đoạn trace chứng minh lỗi và nêu nguyên nhân có thể xảy ra.

```json
[
  {
    "event": "tool",
    "step": 1,
    "name": "get_status",
    "arguments": {
      "provider": "github",
      "component": "Copilot Mission Control"
    },
    "result": {
      "provider": "github",
      "captured_at": "2026-11-09T03:50:47.065020+00:00",
      "overall": {
        "indicator": "none",
        "description": "All Systems Operational"
      },
      "components": [],
      "incidents": [
        {
          "id": "tc28c0wzrnpz",
          "name": "Increased task-related errors for Copilot Mission Control",
          "status": "resolved",
          "updated_at": "2026-11-04T10:01:44.589Z"
        }
      ],
      "matching_incidents_in_last_50": 1,
      "note": "Chỉ tìm theo chuỗi trong 50 incident gần nhất; không tìm thấy không chứng minh không có sự cố.",
      "source": "https://www.githubstatus.com"
    }
  }
]
```

**Nguyên nhân có thể xảy ra:**
- Agent dừng lại quá sớm ngay sau bước gọi `get_status` đầu tiên. Mặc dù đã tìm thấy incident `tc28c0wzrnpz`, agent không gọi tiếp tool `get_incident_details` để đào sâu thông tin.
- Do không đọc chi tiết incident, agent thiếu mốc thời gian chính xác của vòng đời sự cố (bắt đầu lúc 08:45 UTC, kết thúc lúc 10:01 UTC ngày 04/11/2026) và thiếu URL nguồn trực tiếp của incident (`https://stspg.io/hj74883wgn0t`), chỉ dẫn link trang chủ chung chung `githubstatus.com`.
- Hậu quả: LLM Judge đánh giá câu trả lời thiếu chính xác về mặt thời gian, thiếu bằng chứng xác thực và trừ điểm nặng ở tiêu chí Factuality (15/40) và Boundaries (5/15).

## 3. Thay đổi đã thực hiện

- Sửa gì, ở đâu:
  - Cập nhật `SYSTEM_PROMPT` trong `agent.py`: Bổ sung chỉ dẫn tường minh yêu cầu agent khi tìm thấy incident có ID từ `get_status` thì phải chủ động gọi tiếp `get_incident_details` để lấy mốc thời gian chi tiết (bắt đầu, kết thúc) và URL cụ thể của sự cố; hướng dẫn rõ trường `components` rỗng không đồng nghĩa với không có dịch vụ bị ảnh hưởng.
  - Phối hợp với cơ chế Evidence Gate trong `run_agent`: Tự động kiểm tra và yêu cầu bổ sung URL incident vào câu trả lời cuối cùng nếu agent đã xem chi tiết incident thành công.
- Vì sao chọn thay đổi này:
  - Thúc đẩy agent thực hiện điều tra nhiều bước (multi-step investigation) thay vì chỉ kết luận hời hợt sau 1 tool call.
  - Cung cấp đầy đủ bằng chứng cụ thể (timeline chính xác theo giờ UTC, link incident chính thức) đáp ứng đúng tiêu chuẩn đánh giá của Judge.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 77.23 / 100 | 76.82 / 100 |
| Điểm case đã chọn (E5) | 55 / 100 | 75 / 100 (+20 điểm) |
| Số model calls | 50 calls | 53 calls |
| Token, chi phí nếu có | 41,627 tokens (~$0.0105) | 55,273 tokens (~$0.0129) |

- **Lỗi đã giải quyết:**
  - Ở case E5: Agent đã thực hiện điều tra nhiều bước qua `get_incident_details`, trích xuất được khung thời gian chính xác (08:45 – 10:01 UTC ngày 04/11/2026) và dẫn link incident trực tiếp (`https://stspg.io/hj74883wgn0t`). Điểm case E5 tăng vọt từ 55 lên 75 điểm.
  - Nhiều case khác cũng được cải thiện rõ rệt: A5 (tăng từ 35 lên 55 điểm nhờ nêu rõ giới hạn 50 incident), E2 (tăng lên 100), E4 (tăng lên 100), A1 (tăng lên 100), H4 (tăng lên 100).
- **Lỗi còn lại hoặc mới xuất hiện:**
  - Điểm tổng giữa hai lần có sự biến động nhẹ (77.23 vs 76.82) do một số case như E1 hay H2 bị dao động điểm judge tự nhiên (prompt injection / hallucination check của judge có tính xác suất).
  - Ở các case thông tin dài và nhiều mục nhiễu (H1, H6), agent vẫn cần cải thiện khả năng lọc dữ liệu để tối ưu số lượt gọi tool hơn nữa.

## 5. Giới hạn

- **Giới hạn của LLM Judge:** Judge chấm điểm dựa trên mô hình ngôn ngữ (probabilistic). Cùng một câu trả lời ở hai lần chạy khác nhau có thể chênh lệch điểm số nhẹ; điểm số chỉ là một phép đo xấp xỉ chứ không phải chân lý tuyệt đối.
- **Giới hạn của Snapshot:** Bộ dữ liệu là bản sao đóng băng tại ngày 09/11/2026 và chỉ lưu 50 incident gần nhất. Dữ liệu này không phản ánh tình trạng thời gian thực tế của GitHub hay Cloudflare.
- **Giới hạn của việc chạy một lần mỗi phiên bản:** Một lần chạy đơn lẻ chưa đủ để khẳng định độ tin cậy và phương sai của agent trong môi trường thực tế; cần nhiều lần chạy lặp lại để có giá trị trung bình thống kê tin cậy hơn.
