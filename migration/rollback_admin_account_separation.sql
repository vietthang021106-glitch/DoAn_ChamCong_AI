-- Reverses migration/migrate_admin_account.php without deleting any row.
-- Run only against the intended MariaDB database during a maintenance window.
-- The procedure stops unless it can identify exactly one Admin profile and one
-- preserved Admin account. It is safe to rerun if the data re-attachment already
-- succeeded but the final ALTER TABLE did not.

DROP PROCEDURE IF EXISTS rollback_admin_account_separation;
DELIMITER //
CREATE PROCEDURE rollback_admin_account_separation()
BEGIN
    DECLARE v_admin_profile_count INT DEFAULT 0;
    DECLARE v_detached_admin_count INT DEFAULT 0;
    DECLARE v_admin_account_count INT DEFAULT 0;
    DECLARE v_legacy_linked_count INT DEFAULT 0;
    DECLARE v_admin_employee_id INT DEFAULT NULL;
    DECLARE v_admin_account_id INT DEFAULT NULL;
    DECLARE v_legacy_account_id INT DEFAULT NULL;

    SELECT COUNT(*), MIN(nv.MaNV)
      INTO v_admin_profile_count, v_admin_employee_id
    FROM NhanVien nv
    INNER JOIN VaiTro vt ON vt.MaVaiTro = nv.MaVaiTro
    WHERE vt.TenVaiTro = 'Quản trị viên';

    SELECT COUNT(*), MIN(MaTK)
      INTO v_detached_admin_count, v_admin_account_id
    FROM TaiKhoan
    WHERE LoaiTaiKhoan = 'ADMIN' AND MaNV IS NULL;

    SELECT COUNT(*) INTO v_admin_account_count
    FROM TaiKhoan
    WHERE LoaiTaiKhoan = 'ADMIN';

    SELECT COUNT(*), MIN(MaTK)
      INTO v_legacy_linked_count, v_legacy_account_id
    FROM TaiKhoan
    WHERE LoaiTaiKhoan = 'LEGACY' AND MaNV = v_admin_employee_id;

    IF v_admin_profile_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rollback stopped: expected exactly one legacy Admin profile.';
    END IF;

    IF v_admin_account_count = 1 AND v_detached_admin_count = 1 THEN
        IF v_legacy_linked_count <> 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rollback stopped: another account is already linked to the Admin profile.';
        END IF;

        START TRANSACTION;
        UPDATE TaiKhoan
        SET MaNV = v_admin_employee_id, LoaiTaiKhoan = 'LEGACY'
        WHERE MaTK = v_admin_account_id
          AND LoaiTaiKhoan = 'ADMIN'
          AND MaNV IS NULL;

        IF ROW_COUNT() <> 1 THEN
            ROLLBACK;
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rollback stopped: Admin account was not reattached exactly once.';
        END IF;
        COMMIT;
    ELSEIF v_admin_account_count = 0 AND v_detached_admin_count = 0 THEN
        -- Allow retry after the account row was reattached but DDL cleanup failed.
        IF v_legacy_linked_count <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rollback stopped: cannot identify exactly one reattached Admin account.';
        END IF;
    ELSE
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rollback stopped: ambiguous or inconsistent Admin account state.';
    END IF;

    ALTER TABLE TaiKhoan
        DROP CONSTRAINT CK_TaiKhoan_AdminDetached,
        DROP INDEX UQ_TaiKhoan_AdminSingleton,
        DROP COLUMN AdminSingleton,
        DROP COLUMN LoaiTaiKhoan;
END//
DELIMITER ;

CALL rollback_admin_account_separation();
DROP PROCEDURE rollback_admin_account_separation;
