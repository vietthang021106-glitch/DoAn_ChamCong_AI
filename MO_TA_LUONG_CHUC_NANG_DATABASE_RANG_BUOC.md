# 1. LUỒNG HOẠT ĐỘNG CỦA HỆ THỐNG

## 1.1 Quản lý nhân viên

Quản trị viên, gọi ngắn là Admin, tạo hồ sơ bằng họ tên, vai trò, tên đăng nhập và mật khẩu. Hệ thống kiểm tra thông tin, bảo đảm tên đăng nhập chưa được sử dụng và mật khẩu xác nhận khớp với mật khẩu đã nhập.

Sau khi tạo hồ sơ, hệ thống tạo tài khoản để nhân viên đăng nhập. Hai dữ liệu được lưu cùng một giao dịch để bảo đảm đồng bộ. Nếu tạo tài khoản bị lỗi, hồ sơ mới cũng không được giữ lại, tránh có nhân viên nhưng thiếu tài khoản.

Admin tìm nhân viên theo mã, họ tên hoặc tên đăng nhập để sửa hồ sơ, tài khoản. Nhập mật khẩu mới khi cần đổi; để trống thì giữ mật khẩu cũ. Hồ sơ cũ chưa có tài khoản có thể được bổ sung tài khoản sau.

Người dùng đăng nhập bằng tên đăng nhập và mật khẩu. Hệ thống kiểm tra tài khoản và vai trò. Admin được quản lý dữ liệu chung; nhân viên chỉ xem thông tin của mình. Đăng xuất kết thúc phiên làm việc.

## 1.2 Đăng ký khuôn mặt

Nhân viên mới có hồ sơ và tài khoản nhưng chưa có dữ liệu khuôn mặt. Admin mở hồ sơ và bắt đầu đăng ký. Nhân viên thực hiện năm hướng: chính diện, nghiêng trái, nghiêng phải, ngẩng nhẹ và cúi nhẹ.

Mỗi mẫu cần đúng một khuôn mặt và đúng hướng yêu cầu. Mẫu chưa phù hợp thì lấy lại. Chỉ khi đủ năm mẫu hợp lệ và xác nhận lưu, hệ thống mới lưu cả bộ cho nhân viên.

Hệ thống lưu dữ liệu đặc trưng khuôn mặt để phục vụ nhận diện, kèm ảnh mẫu tương ứng. Một nhân viên có nhiều mẫu. Có hồ sơ và đã đăng ký khuôn mặt là hai trạng thái riêng.

Khi đăng ký lại, bộ cũ được giữ trong lúc thu bộ mới. Đủ mẫu mới và lưu thành công thì hệ thống thay thế. Nếu hủy hoặc lưu lỗi, bộ cũ vẫn còn. Hồ sơ, tài khoản và lịch sử chấm công không bị mất.

## 1.3 Tạo ca và phân ca

Admin tạo ca bằng tên, giờ bắt đầu và giờ kết thúc, chẳng hạn ca hành chính 08:00–17:00. Ca đang sử dụng được chọn để phân cho nhân viên. Ca không còn dùng có thể ngừng sử dụng rồi kích hoạt lại.

Admin chọn nhân viên + ca + ngày để phân ca. Mỗi phân ca cho biết ai làm ca nào vào ngày nào. Một nhân viên trong một ngày chỉ có một ca; đổi ca sẽ cập nhật ca của ngày đó.

Ca đã có chấm công không được sửa giờ, tránh thay đổi cách đánh giá lịch sử. Ca còn dữ liệu liên quan không được xóa tùy ý. Nếu đổi giờ làm việc, Admin có thể tạo ca khác để phân cho những ngày tiếp theo.

## 1.4 Chấm công

Giả sử Nguyễn Văn A được phân ca 08:00–17:00. Khi danh tính A đã được xác định và yêu cầu chấm công được gửi đến, hệ thống tìm phân ca hôm nay, rồi kiểm tra giờ vào/ra đã có. Dữ liệu này quyết định lần chấm công là vào hay ra.

**Lần quét đầu tiên:** Có phân ca và chưa chấm công hôm nay thì ghi giờ vào. A vào lúc 07:55 hoặc đúng 08:00 được đánh giá đúng giờ; vào 08:10 là đi trễ vì sau giờ bắt đầu ca.

Hệ thống lưu nhân viên, giờ vào, ca, thiết bị được ghi nhận và ảnh vào nếu có. Giờ ra còn trống. Ảnh được lưu khi camera cung cấp được hình ảnh lúc chấm công.

**Lần quét thứ hai:** Đã có giờ vào nhưng chưa có giờ ra thì ghi giờ ra vào cùng lượt. A ra 16:30 là về sớm; ra 17:00 hoặc 17:05 là đúng giờ ra. Hệ thống lưu giờ ra, ảnh ra nếu có.

**Quét thêm lần nữa:** Đã đủ giờ vào và ra thì giữ nguyên chấm công trong ngày, không ghi đè giờ hoặc ảnh. Lần quét này có thể được lưu vào lịch sử quét để kiểm tra.

Ảnh vào/ra là bằng chứng tại từng thời điểm chấm công, được lưu riêng với ảnh đăng ký khuôn mặt. Nhân viên xem ảnh của mình; Admin đối chiếu ảnh với giờ và ca.

## 1.5 Quét thất bại

Các tình huống cần kiểm tra gồm không nhận diện được, không có phân ca, ca đã kết thúc, đã đủ vào/ra hoặc có nhiều khuôn mặt. Lần quét chưa được chấp nhận không được xem là chấm công thành công.

Khi ghi lịch sử, hệ thống lưu thời gian, lý do, ảnh đúng lần quét, nhân viên nếu biết, ca và thiết bị nếu có. Chưa nhận diện được thì thông tin nhân viên để trống.

Lịch sử giúp kiểm tra khi nhân viên báo đã quét nhưng không thấy chấm công. Admin đối chiếu thời gian, lý do và ảnh. Chấm công thành công lưu ở lịch sử chấm công; quét thất bại hoặc bị từ chối lưu ở lịch sử quét.

Cùng lỗi trên cùng thiết bị và cùng nhân viên, nếu biết, trong khoảng 30 giây chỉ lưu một lần. Điều này tránh tạo nhiều ảnh giống nhau khi một người đứng trước camera.

## 1.6 Sức khỏe và cảnh báo

Hệ thống lưu nhịp tim, SpO2 và thời gian theo nhân viên. Một người có nhiều bản ghi ở những thời điểm khác nhau. Admin lọc theo nhân viên, khoảng ngày; nhân viên chỉ xem lịch sử của mình.

Khi có thông tin bất thường được chuyển đến, hệ thống có thể lưu trạng thái và tạo cảnh báo. Cảnh báo gồm người liên quan, thời gian, nội dung, loại và thiết bị nếu có. Không phải mọi số đo sức khỏe đều tự tạo cảnh báo.

Admin xem sức khỏe và cảnh báo toàn hệ thống; nhân viên chỉ xem dữ liệu của mình. Lịch sử được giữ theo thời gian để tra cứu và đối chiếu khi cần.

## 1.7 Theo dõi dữ liệu

Admin tra cứu nhân viên, phân ca, chấm công, lịch sử quét, sức khỏe và cảnh báo. Thông tin thiết bị đi kèm lần chấm công hoặc lần quét. Có thể lọc lịch sử theo nhân viên, ngày; lịch sử quét còn lọc theo lý do và thiết bị.

Phần tổng quan tổng hợp số nhân viên, đã đăng ký khuôn mặt, có phân ca, đã chấm công, đang làm, đi trễ, về sớm, chưa chấm công; kèm hoạt động bảy ngày và cảnh báo gần đây. Số chưa chấm công có thể gồm người chưa phân ca.

Trang của tôi cho nhân viên xem ca, giờ vào/ra, ảnh, sức khỏe và cảnh báo. Hệ thống dựa vào người đang đăng nhập để lấy dữ liệu. Nhân viên không được xem dữ liệu người khác bằng cách thay mã nhân viên hoặc mã ảnh.

# 2. CƠ SỞ DỮ LIỆU

Cơ sở dữ liệu giữ hồ sơ, tài khoản, lịch làm việc và các lịch sử phát sinh. Những dữ liệu này được liên kết để tra cứu theo nhân viên.

| Bảng | Dùng để lưu |
|---|---|
| VaiTro | Vai trò người dùng |
| NhanVien | Thông tin nhân viên |
| TaiKhoan | Tài khoản đăng nhập |
| FaceEmbedding | Các mẫu khuôn mặt |
| CaLamViec | Danh mục ca làm việc |
| PhanCaNhanVien | Nhân viên làm ca nào theo ngày |
| ChamCong | Giờ vào, giờ ra, ảnh vào và ảnh ra |
| LichSuQuet | Những lần quét thất bại hoặc bị từ chối và ảnh |
| LoaiLyDoQuet | Danh mục 5 lý do quét thất bại cố định |
| ThietBi | Thông tin thiết bị |
| LichSuSucKhoe | Nhịp tim và SpO2 theo thời gian |
| LichSuTrangThai | Lịch sử trạng thái của nhân viên |
| DanhMucBieuHien | Danh mục biểu hiện |
| LoaiCanhBao | Các loại cảnh báo |
| CanhBao | Các cảnh báo đã phát sinh |

Một vai trò áp dụng cho nhiều nhân viên. Mỗi nhân viên thường được tạo một tài khoản gắn với hồ sơ của mình. Một người có thể có nhiều mẫu khuôn mặt, phân ca qua các ngày, dữ liệu sức khỏe và cảnh báo.

Một ca có thể được phân cho nhiều nhân viên. Phân ca gắn nhân viên với ca và ngày. Chấm công liên kết nhân viên, ca và thiết bị. Lịch sử quét cũng gắn các thông tin này nếu có; người chưa nhận diện được thì để trống nhân viên.

Danh mục biểu hiện giải thích trạng thái; danh mục loại cảnh báo phân nhóm cảnh báo. Các liên kết giúp tập hợp những dữ liệu liên quan khi tra cứu một nhân viên.

# 3. CÁC TRƯỜNG HỢP ĐẶC BIỆT

| Trường hợp | Hệ thống xử lý |
|---|---|
| Nhân viên chưa đăng ký khuôn mặt | Vẫn có hồ sơ và tài khoản nhưng chưa có mẫu để dùng nhận diện khuôn mặt. |
| Nhân viên chưa có phân ca | Không ghi nhận chấm công cho ngày đó. |
| Quét lần đầu trong ngày | Có phân ca và chưa có chấm công thì ghi giờ vào. |
| Đã có giờ vào, chưa có giờ ra | Lần chấm công tiếp theo ghi giờ ra vào cùng lượt. |
| Đã có giờ vào và giờ ra | Giữ nguyên chấm công; có thể ghi nhận lần quét bị từ chối. |
| Vào sau giờ bắt đầu | Được đánh giá đi trễ. |
| Ra trước giờ kết thúc | Được đánh giá về sớm. |
| Không nhận diện được | Chưa có danh tính để chấm công; nếu ghi lịch sử quét thì lưu lý do và ảnh. |
| Có nhiều khuôn mặt | Cần xác định lại một nhân viên; có thể lưu lý do nhiều khuôn mặt khi phần ghi lịch sử được gọi. |
| Ca đã kết thúc nhưng chưa có giờ vào | Chức năng chặn lần chấm công này đang được chuẩn bị, chưa áp dụng tự động. |
| Quét lỗi liên tục | Cùng thiết bị, cùng lỗi và cùng nhân viên nếu biết, trong 30 giây chỉ lưu một lần. |

**Một ví dụ xuyên suốt**

1. Admin tạo hồ sơ Nguyễn Văn A và tài khoản đăng nhập tương ứng.
2. Admin đăng ký đủ năm góc khuôn mặt rồi lưu bộ mẫu của A.
3. Admin phân cho A ca 08:00–17:00 trong ngày làm việc.
4. Lúc 07:55, khi danh tính A đã được xác định, lần chấm công đầu ghi giờ vào và ảnh vào nếu có; A được đánh giá đúng giờ.
5. Lúc 17:05, lần chấm công thứ hai ghi giờ ra và ảnh ra vào cùng lượt.
6. Nếu A quét lần ba, giờ và ảnh chấm công đã lưu không thay đổi.
7. Nếu người lạ quét, chưa có danh tính nhân viên để ghi chấm công.
8. Khi ghi lịch sử quét, lần không nhận diện được sẽ được lưu kèm lý do và ảnh để Admin kiểm tra.
9. Sau đó Admin và A có thể xem lại dữ liệu theo quyền của mình.

Hiện còn một số phần chưa nối tự động: nhận diện với chấm công, ghi lịch sử quét thật, đồng bộ sức khỏe/cảnh báo và tích hợp thiết bị thực tế. Việc chặn check-in sau khi ca kết thúc cũng chưa được áp dụng tự động.


# 4. CẢI THIỆN HỆ THỐNG

Các cải thiện tập trung vào cách tổ chức mã nguồn, quản lý hồ sơ và tài khoản, liên kết lịch làm việc với chấm công, lưu bằng chứng và kiểm tra lỗi. Nội dung dưới đây làm rõ thay đổi đã thực hiện, cách người dùng sử dụng và cách dữ liệu đi qua từng chức năng.

## 4.1. Chuyển cấu trúc Web sang MVC

Web được chia thành Model, View và Controller để tách phần làm việc với dữ liệu khỏi phần hiển thị. Model đọc và ghi database theo chức năng được hỗ trợ. View nhận dữ liệu để hiển thị biểu mẫu, bộ lọc và bảng. Controller tiếp nhận yêu cầu, kiểm tra quyền, gọi xử lý phù hợp rồi chọn màn hình hoặc trả lỗi.

Khi Admin mở danh sách nhân viên, Controller nhận yêu cầu, gọi Model đọc hồ sơ cùng thông tin tài khoản, sau đó chuyển kết quả cho View. Khi Admin gửi biểu mẫu thêm hoặc sửa, Controller kiểm tra thông tin trước khi chuyển sang bước lưu. Cách tổ chức này giúp dễ tìm vị trí cần sửa, hạn chế việc chỉnh giao diện làm ảnh hưởng truy vấn và thuận tiện phát triển từng chức năng.

## 4.2. Cải thiện quản lý nhân viên và tài khoản

Quản lý hồ sơ và đăng nhập được đưa vào một chức năng thống nhất. Admin nhập họ tên, vai trò, tên đăng nhập và mật khẩu rồi nhấn tạo. Hệ thống kiểm tra dữ liệu, kiểm tra tên đăng nhập đã tồn tại chưa và băm mật khẩu mới. Sau đó hệ thống tạo NhanVien, lấy MaNV vừa sinh và tạo TaiKhoan gắn với MaNV đó.

Hai bước ghi dữ liệu được lưu cùng nhau. Nếu tạo TaiKhoan lỗi, NhanVien vừa tạo cũng không được giữ lại. Nhờ vậy, chức năng không báo hoàn tất khi mới lưu được hồ sơ mà chưa có tài khoản đăng nhập.

Khi sửa, Admin chọn nhân viên để hệ thống lấy hồ sơ cùng tài khoản liên quan. Admin thay thông tin hoặc tên đăng nhập; có mật khẩu mới thì băm và cập nhật, để trống thì giữ mật khẩu cũ. Hồ sơ cũ thiếu TaiKhoan có thể được bổ sung. Vai trò gắn với nhân viên được dùng khi đăng nhập, giúp hồ sơ, tài khoản và quyền sử dụng nhất quán hơn.

## 4.3. Cải thiện quản lý khuôn mặt

Dữ liệu nhận diện được quản lý thành nhiều mẫu FaceEmbedding cho một nhân viên, thay vì chỉ dựa vào một ảnh hồ sơ. Admin mở nhân viên, chọn đăng ký khuôn mặt rồi lần lượt thu mẫu chính diện, nghiêng trái, nghiêng phải, ngẩng nhẹ và cúi nhẹ. Hệ thống kiểm tra đủ mẫu hợp lệ trước khi lưu toàn bộ theo MaNV.

Mỗi mẫu có dữ liệu đặc trưng, ảnh khuôn mặt và mã nhân viên liên kết. Nhờ dùng chung MaNV, các mẫu được xác định thuộc cùng một người nhưng vẫn được quản lý riêng với hồ sơ và tài khoản.

Khi đăng ký lại, bộ cũ được giữ trong lúc thu và kiểm tra bộ mới. Chỉ khi bộ mới lưu thành công, hệ thống mới hoàn tất việc thay thế. Nếu hủy hoặc lưu thất bại, bộ cũ vẫn còn. Cải thiện này tránh mất dữ liệu khuôn mặt đang dùng khi đăng ký lại gặp lỗi, đồng thời không làm thay đổi hồ sơ hay lịch sử chấm công.

## 4.4. Cải thiện quản lý ca làm việc

Chức năng được chia rõ thành quản lý ca và phân ca. Để tạo ca, Admin nhập tên, giờ bắt đầu và giờ kết thúc. Hệ thống kiểm tra thông tin rồi tạo CaLamViec; ca đang hoạt động có thể được chọn trong phân ca. Một ca dùng được cho nhiều nhân viên nên không phải nhập lại giờ làm cho từng người.

Khi phân ca, Admin chọn nhân viên, ca và ngày. Hệ thống lưu PhanCaNhanVien theo nhân viên và ngày làm việc: chưa có thì tạo mới, đã có thì cập nhật MaCa của ngày đó. Một nhân viên chỉ có một phân ca mỗi ngày, giúp lúc chấm công xác định được đúng lịch cần dùng.

Khi Admin ngừng sử dụng ca, TrangThai chuyển sang không hoạt động. Ca không còn được dùng cho phân ca mới nhưng lịch sử cũ vẫn giữ và có thể kích hoạt lại khi cần. Ca đã có ChamCong không được đổi giờ; ca còn phân công hoặc chấm công không được xóa. Việc giữ giờ ca cũ giúp kết quả đi trễ, về sớm trong lịch sử không bị thay đổi.

## 4.5. Cải thiện chức năng chấm công

Chấm công được tổ chức dựa trên một bản ghi vào/ra trong ngày. Giả sử Nguyễn Văn A làm ca 08:00–17:00. Khi nhận được MaNV và yêu cầu chấm công, hệ thống kiểm tra nhân viên, tìm PhanCaNhanVien hôm nay, lấy CaLamViec rồi tìm ChamCong của ngày đó. Không có phân ca thì không ghi nhận chấm công.

Nếu có phân ca và chưa có ChamCong, lần này được hiểu là check-in. Hệ thống tạo bản ghi với MaNV, MaCa, MaTB được ghi nhận, GioVao và AnhVao nếu có ảnh; giờ ra còn trống. GioVao bằng hoặc trước GioBatDau là đúng giờ, sau GioBatDau là đi trễ. Vì vậy, A vào 07:55 được đánh giá đúng giờ, còn 08:10 là đi trễ.

Nếu đã có GioVao nhưng chưa có GioRa, lần tiếp theo là check-out. Hệ thống cập nhật chính bản ghi đó bằng GioRa và AnhRa nếu có. GioRa trước GioKetThuc là về sớm; bằng hoặc sau giờ kết thúc thì không về sớm. A ra 16:30 là về sớm, ra 17:05 không bị tính về sớm.

Khi đã có đủ giờ vào và ra, quét tiếp không tạo ChamCong mới và không ghi đè giờ hoặc ảnh cũ. Nhờ gom vào/ra trong cùng bản ghi, dữ liệu ngày công dễ xem, lọc và đối chiếu hơn các lượt rời.

## 4.6. Cải thiện bằng chứng chấm công

Ảnh được lưu theo đúng thời điểm vào và ra. Khi check-in có ảnh từ camera, hệ thống lưu vào AnhVao gắn với GioVao. Khi check-out có ảnh, hệ thống lưu vào AnhRa gắn với GioRa. Không lấy được ảnh thì phần ảnh để trống, thời gian chấm công vẫn có thể được ghi nhận.

Khi xem lịch sử, Admin chọn ảnh; hệ thống kiểm tra quyền, lấy ảnh đúng MaCC và đúng loại vào hoặc ra rồi hiển thị. Nhân viên chỉ được xem ảnh thuộc ChamCong của MaNV đang đăng nhập. Ảnh trong FaceEmbedding phục vụ đăng ký và nhận diện; AnhVao, AnhRa là ảnh tại lần chấm công. Việc tách này giúp đối chiếu phản ánh bằng ảnh đúng thời điểm, không nhầm với ảnh mẫu.

## 4.7. Cải thiện xử lý quét thất bại

Một cải thiện quan trọng là bổ sung LichSuQuet bên cạnh ChamCong. ChamCong giữ dữ liệu chấm công thành công; LichSuQuet giữ bằng chứng của lần quét lỗi hoặc bị từ chối. Nhờ tách riêng, các lượt không hợp lệ không bị trộn vào dữ liệu giờ làm.

Luồng ghi lịch sử đã được chuẩn bị để khi kết quả quét không được chấp nhận, phần xử lý xác định lý do, lấy ảnh quét rồi tạo LichSuQuet. Các lý do gồm KHONG_NHAN_DIEN khi chưa biết nhân viên, NHIEU_KHUON_MAT khi có nhiều người, KHONG_CO_PHAN_CA khi đã biết người nhưng không có lịch hôm đó, CA_DA_KET_THUC cho trường hợp ca đã kết thúc và DA_HOAN_THANH khi đã đủ giờ vào/ra. Đây là các nhóm lý do được hỗ trợ lưu; không đồng nghĩa mọi nhánh đã tự động được ghi.

Một bản ghi lưu ThoiGianQuet, MaLyDo, AnhQuet; có thể kèm MaNV, MaTB, MaCa, SoKhuonMat, DoTinCay và ChiTiet. LichSuQuet.MaLyDo liên kết LoaiLyDoQuet.MaLyDo thay cho chuỗi LyDo cũ. Không nhận diện được hoặc có nhiều khuôn mặt thì MaNV để trống. Với lượt đã hoàn thành vào/ra, ChamCong cũ được giữ nguyên; lịch sử quét là nơi riêng để kiểm tra lần bị từ chối.

LoaiLyDoQuet lưu loại lý do cố định, còn LichSuQuet lưu từng lần quét thực tế. Danh mục gồm MaLyDo (khóa chính), MaCode (mã duy nhất), TenLyDo (tên hiển thị), MoTa và TrangThai (đang sử dụng hay không). Service nhận MaCode và model tra MaLyDo để lưu; giao diện lấy TenLyDo qua JOIN, không phụ thuộc ID cố định.

Để tra cứu, Admin mở Chấm công, chuyển tab Lịch sử quét, lọc theo ngày, nhân viên, lý do hoặc thiết bị, rồi mở ảnh đã lưu. Luồng này hỗ trợ kiểm tra phản ánh “em đã đứng quét nhưng không có công”. Một số trường hợp vẫn đang tiếp tục được nối tự động với luồng quét thực tế.

## 4.8. Cải thiện chống lưu lỗi quét liên tục

Trước khi ghi LichSuQuet, phần xử lý kiểm tra trong 30 giây gần nhất có bản ghi cùng MaTB, MaLyDo và MaNV nếu có hay chưa. Chưa có thì lưu; đã có thì bỏ qua lần ghi lặp. Với người chưa xác định được, việc so sánh dùng trạng thái chưa có MaNV cùng thiết bị và lý do.

Ví dụ, lỗi không nhận diện được lúc 10:00:00 được lưu. Lỗi cùng nhóm lúc 10:00:05 không lưu thêm; đến 10:00:31 có thể lưu lần mới. Quy tắc áp dụng khi phần ghi lịch sử được gọi, giúp tránh hàng chục ảnh giống nhau do camera xử lý nhiều khung hình, giảm dung lượng và giữ lịch sử dễ kiểm tra.

## 4.9. Cải thiện Sức khỏe & Cảnh báo

Admin vào một khu vực chung có tab Sức khỏe và Cảnh báo. Ở tab Sức khỏe, Admin chọn nhân viên hoặc khoảng ngày; hệ thống lấy LichSuSucKhoe phù hợp và hiển thị nhịp tim, SpO2 cùng thời gian. Chuyển sang tab Cảnh báo, hệ thống lấy CanhBao để hiển thị nhân viên, loại, nội dung và thời điểm phát sinh.

Hai phần dùng cách lọc và tra cứu thống nhất, giúp đối chiếu dữ liệu liên quan mà không phải tìm ở nhiều khu vực. Nhân viên xem sức khỏe và cảnh báo của mình trong Trang của tôi. Các khối nhịp tim gần nhất, SpO2 gần nhất hoặc sức khỏe gần nhất không được lặp lại, giúp người dùng tập trung vào lịch sử cần kiểm tra.

## 4.10. Cải thiện cơ sở dữ liệu

Các thay đổi về database hỗ trợ trực tiếp việc chuyển từ hồ sơ sang tài khoản, lịch làm việc, chấm công và tra cứu. Mỗi nhóm dữ liệu có nhiệm vụ riêng nhưng liên kết qua mã để các chức năng phối hợp được với nhau.

### NhanVien và TaiKhoan

Khi NhanVien được tạo, MaNV mới được dùng để tạo TaiKhoan. Tài khoản biết mình thuộc hồ sơ nào; lúc đăng nhập, hệ thống từ tài khoản tìm lại đúng nhân viên và vai trò. Cách liên kết này hỗ trợ quản lý người dùng và lấy dữ liệu cá nhân mà không cần lưu lặp thông tin hồ sơ trong tài khoản.

### FaceEmbedding

MaNV liên kết một nhân viên với nhiều mẫu FaceEmbedding. Khi Admin mở hồ sơ, hệ thống lấy các mẫu theo mã đó; khi đăng ký lại, bộ mẫu của đúng người được thay mà không sửa hồ sơ. Dữ liệu mẫu có nơi quản lý riêng, thuận tiện kiểm tra ảnh và giữ các chức năng khác độc lập với việc thay khuôn mặt.

### CaLamViec và PhanCaNhanVien

Admin tạo CaLamViec rồi dùng mã ca để phân cho nhân viên theo ngày trong PhanCaNhanVien. Khi chấm công, hệ thống dùng MaNV và ngày tìm phân ca, lấy MaCa rồi đọc GioBatDau, GioKetThuc. Các giờ này là căn cứ đánh giá đi trễ, về sớm, giúp lịch làm việc liên kết trực tiếp với kết quả chấm công.

### TrangThai của ca

Khi ca ngừng dùng, TrangThai khiến ca không được chọn cho phân ca mới. Các lịch phân ca và chấm công đã có vẫn tham chiếu tới mã ca cũ để tra cứu. Vì không phải xóa rồi tạo lại, lịch sử giữ được thông tin liên quan và ca có thể được kích hoạt lại khi cần.

### ChamCong

Lần đầu hệ thống thêm bản ghi chứa GioVao; lần hai cập nhật cùng bản ghi để thêm GioRa. AnhVao và AnhRa đi cùng thời điểm tương ứng khi có ảnh. Luồng ghi này giúp một bản ghi phản ánh ngày công, phục vụ xem người đang làm, đã ra và các trạng thái theo giờ ca.

### LichSuQuet

Khi phần ghi lỗi được gọi, dữ liệu quét không hợp lệ được lưu riêng trong LichSuQuet thay vì tạo hoặc sửa ChamCong. Admin tra cứu bảng lịch sử rồi mở AnhQuet của lần cần kiểm tra. Cấu trúc này giữ dữ liệu giờ làm riêng với dữ liệu phục vụ giải thích sự cố.

### Ràng buộc phân ca

MaNV và NgayLamViec chỉ có một bản ghi phân ca. Khi Admin phân lại, hệ thống cập nhật ca trong bản ghi hiện có. Nhờ đó, lúc chấm công theo ngày không phát sinh nhiều lịch cho cùng một nhân viên, giảm nhầm lẫn khi chọn ca để so giờ vào/ra.

### Liên kết dữ liệu bằng mã

MaNV nối hồ sơ với tài khoản, mẫu khuôn mặt, phân ca, chấm công, sức khỏe và cảnh báo. MaCa nối lịch làm việc với giờ ca; MaTB cho biết thiết bị gắn với lần chấm công hoặc quét. Khi hiển thị, hệ thống liên kết để lấy họ tên, tên ca, loại thiết bị thay vì lưu lặp các tên này trong từng bản ghi.

### Loại bỏ dữ liệu môi trường

Schema hiện tại không còn định nghĩa ThongSoMoiTruong; Web không còn truy vấn và hiển thị phần môi trường. Việc bỏ nhóm dữ liệu ngoài phạm vi đang dùng giúp chức năng tập trung vào nhân viên, khuôn mặt, ca, chấm công, sức khỏe và cảnh báo, giảm phần lưu trữ và xử lý không phục vụ thao tác chính.

## 4.11. Cải thiện phân quyền

Sau khi đăng nhập, hệ thống từ TaiKhoan xác định MaNV, đọc nhân viên và VaiTro rồi lưu thông tin vào phiên đăng nhập, gọi là Session. Admin được vào chức năng quản trị; nhân viên được chuyển tới Trang của tôi. Khi lấy dữ liệu cá nhân, hệ thống dùng MaNV trong Session để truy vấn đúng hồ sơ, ca, chấm công, sức khỏe và cảnh báo.

Khi nhân viên mở ảnh bằng MaCC trên đường dẫn, hệ thống tìm bản ghi thuộc đồng thời MaCC đó và MaNV đang đăng nhập. Đúng chủ sở hữu và có ảnh thì trả ảnh; không tìm thấy ảnh thuộc người đó thì không trả dữ liệu. Vì vậy, thay mã ảnh trên đường dẫn không cho phép xem ảnh người khác.

LichSuQuet và ảnh quét lỗi chỉ dành cho Admin. Cách phân quyền này áp dụng khi xử lý yêu cầu và truy vấn dữ liệu, không chỉ ẩn menu, giúp bảo vệ cả chức năng quản trị lẫn dữ liệu cụ thể.

## 4.12. Cải thiện giao diện

Khi chọn Chấm công, Admin vào khu vực có hai tab Chấm công và Lịch sử quét. Tab Chấm công đưa ra bộ lọc cùng bảng giờ vào/ra; tab Lịch sử quét đưa ra bộ lọc và bảng lỗi quét. Sức khỏe & Cảnh báo cũng có hai tab trong một khu vực. Bộ lọc nằm ngay trên bảng liên quan để chọn điều kiện rồi xem kết quả tại chỗ.

Giao diện giảm tiêu đề lặp, mô tả dài và thông tin tóm tắt trùng, tập trung chiều rộng nội dung cho bảng và thao tác tra cứu. Dashboard giữ các số liệu nhân viên, phân ca, chấm công, trạng thái, hoạt động bảy ngày và cảnh báo; không đưa lại môi trường hoặc khối sức khỏe gần nhất. Những thay đổi này giúp ít phải chuyển khu vực và dễ hiểu nơi cần thao tác.
