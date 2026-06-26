-- Convert Canon captured_at from EXIF wall-clock to true UTC.
-- target = wall_clock - EXIF offset (own tag, else the day's shared offset).
-- Phone photos (already UTC) untouched. Absolute values: idempotent & re-runnable.
-- effective_at is refreshed by the BEFORE UPDATE trigger.
BEGIN;
UPDATE photos SET captured_at = '2025-12-30 12:21:04'
  WHERE original_filename = '00.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:43:23'
  WHERE original_filename = '036A0478.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:47:43'
  WHERE original_filename = '036A0479.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:47:45'
  WHERE original_filename = '036A0480.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:47:48'
  WHERE original_filename = '036A0481.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:47:51'
  WHERE original_filename = '036A0482.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:47:54'
  WHERE original_filename = '036A0483.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:48:01'
  WHERE original_filename = '036A0484.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:48:05'
  WHERE original_filename = '036A0485.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:48:08'
  WHERE original_filename = '036A0486.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:36'
  WHERE original_filename = '036A0487.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:39'
  WHERE original_filename = '036A0488.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:42'
  WHERE original_filename = '036A0489.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:45'
  WHERE original_filename = '036A0490.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:47'
  WHERE original_filename = '036A0491.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:49'
  WHERE original_filename = '036A0492.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:53'
  WHERE original_filename = '036A0493.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:55'
  WHERE original_filename = '036A0494.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:57'
  WHERE original_filename = '036A0495.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:00'
  WHERE original_filename = '036A0496.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:03'
  WHERE original_filename = '036A0497.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:40'
  WHERE original_filename = '036A0498.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:43'
  WHERE original_filename = '036A0499.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:45'
  WHERE original_filename = '036A0500.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:48'
  WHERE original_filename = '036A0501.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:56'
  WHERE original_filename = '036A0502.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:51:58'
  WHERE original_filename = '036A0503.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:52:01'
  WHERE original_filename = '036A0504.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:52:03'
  WHERE original_filename = '036A0505.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:52:05'
  WHERE original_filename = '036A0506.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:52:07'
  WHERE original_filename = '036A0507.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:46'
  WHERE original_filename = '036A0508.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:47'
  WHERE original_filename = '036A0509.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:50'
  WHERE original_filename = '036A0510.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:51'
  WHERE original_filename = '036A0511.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:54'
  WHERE original_filename = '036A0512.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:58'
  WHERE original_filename = '036A0513.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:00'
  WHERE original_filename = '036A0514.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:03'
  WHERE original_filename = '036A0515.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:06'
  WHERE original_filename = '036A0516.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:10'
  WHERE original_filename = '036A0517.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:20'
  WHERE original_filename = '036A0518.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:21'
  WHERE original_filename = '036A0519.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:22'
  WHERE original_filename = '036A0520.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:24'
  WHERE original_filename = '036A0521.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:25'
  WHERE original_filename = '036A0522.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:27'
  WHERE original_filename = '036A0523.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:54:29'
  WHERE original_filename = '036A0524.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:14'
  WHERE original_filename = '036A0526.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:18'
  WHERE original_filename = '036A0527.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:24'
  WHERE original_filename = '036A0528.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:27'
  WHERE original_filename = '036A0529.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:29'
  WHERE original_filename = '036A0530.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:33'
  WHERE original_filename = '036A0531.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:35'
  WHERE original_filename = '036A0532.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:41'
  WHERE original_filename = '036A0533.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:44'
  WHERE original_filename = '036A0534.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:48'
  WHERE original_filename = '036A0535.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:52'
  WHERE original_filename = '036A0536.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:54'
  WHERE original_filename = '036A0537.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:56:58'
  WHERE original_filename = '036A0538.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:57:01'
  WHERE original_filename = '036A0539.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:57:05'
  WHERE original_filename = '036A0540.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:19'
  WHERE original_filename = '036A0541.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:22'
  WHERE original_filename = '036A0542.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:24'
  WHERE original_filename = '036A0543.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:27'
  WHERE original_filename = '036A0544.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:29'
  WHERE original_filename = '036A0545.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:34'
  WHERE original_filename = '036A0546.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:37'
  WHERE original_filename = '036A0547.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:40'
  WHERE original_filename = '036A0548.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:58:54'
  WHERE original_filename = '036A0549.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:40'
  WHERE original_filename = '036A0550.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:42'
  WHERE original_filename = '036A0551.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:45'
  WHERE original_filename = '036A0552.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:47'
  WHERE original_filename = '036A0553.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:48'
  WHERE original_filename = '036A0554.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:50'
  WHERE original_filename = '036A0555.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:52'
  WHERE original_filename = '036A0556.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:54'
  WHERE original_filename = '036A0557.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:56'
  WHERE original_filename = '036A0558.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:59:59'
  WHERE original_filename = '036A0559.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:01'
  WHERE original_filename = '036A0560.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:05'
  WHERE original_filename = '036A0561.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:07'
  WHERE original_filename = '036A0562.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:09'
  WHERE original_filename = '036A0563.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:12'
  WHERE original_filename = '036A0564.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:14'
  WHERE original_filename = '036A0565.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:16'
  WHERE original_filename = '036A0566.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:00:21'
  WHERE original_filename = '036A0567.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:41:18'
  WHERE original_filename = '036A0568.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:41:25'
  WHERE original_filename = '036A0569.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:32'
  WHERE original_filename = '036A0570.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:35'
  WHERE original_filename = '036A0571.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:40'
  WHERE original_filename = '036A0572.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:43'
  WHERE original_filename = '036A0573.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:46'
  WHERE original_filename = '036A0574.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:48'
  WHERE original_filename = '036A0575.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:45:50'
  WHERE original_filename = '036A0576.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:19'
  WHERE original_filename = '036A0577.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:20'
  WHERE original_filename = '036A0578.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:22'
  WHERE original_filename = '036A0579.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:24'
  WHERE original_filename = '036A0580.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:27'
  WHERE original_filename = '036A0581.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:30'
  WHERE original_filename = '036A0582.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:46'
  WHERE original_filename = '036A0583.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:48'
  WHERE original_filename = '036A0584.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:50'
  WHERE original_filename = '036A0585.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:53'
  WHERE original_filename = '036A0586.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:55'
  WHERE original_filename = '036A0587.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:47:58'
  WHERE original_filename = '036A0588.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:00'
  WHERE original_filename = '036A0589.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:02'
  WHERE original_filename = '036A0590.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:04'
  WHERE original_filename = '036A0591.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:27'
  WHERE original_filename = '036A0592.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:29'
  WHERE original_filename = '036A0593.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:32'
  WHERE original_filename = '036A0594.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:34'
  WHERE original_filename = '036A0595.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:48:38'
  WHERE original_filename = '036A0597.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:49:06'
  WHERE original_filename = '036A0598.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:51:14'
  WHERE original_filename = '036A0599.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:51:25'
  WHERE original_filename = '036A0600.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:54:27'
  WHERE original_filename = '036A0601.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:55:04'
  WHERE original_filename = '036A0602.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:55:34'
  WHERE original_filename = '036A0603.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:55:36'
  WHERE original_filename = '036A0604.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:55:37'
  WHERE original_filename = '036A0605.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:55:39'
  WHERE original_filename = '036A0606.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:00'
  WHERE original_filename = '036A0607.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:01'
  WHERE original_filename = '036A0608.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:12'
  WHERE original_filename = '036A0609.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:14'
  WHERE original_filename = '036A0610.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:16'
  WHERE original_filename = '036A0611.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:18'
  WHERE original_filename = '036A0612.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:43'
  WHERE original_filename = '036A0613.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:45'
  WHERE original_filename = '036A0614.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:47'
  WHERE original_filename = '036A0615.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:48'
  WHERE original_filename = '036A0616.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:50'
  WHERE original_filename = '036A0617.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:51'
  WHERE original_filename = '036A0618.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:56'
  WHERE original_filename = '036A0619.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 11:59:58'
  WHERE original_filename = '036A0620.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:05:54'
  WHERE original_filename = '036A0621.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:05:56'
  WHERE original_filename = '036A0622.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:05:57'
  WHERE original_filename = '036A0623.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:05:59'
  WHERE original_filename = '036A0624.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:06:13'
  WHERE original_filename = '036A0625.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:08:08'
  WHERE original_filename = '036A0626.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:08:25'
  WHERE original_filename = '036A0627.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:08:38'
  WHERE original_filename = '036A0628.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:10:54'
  WHERE original_filename = '036A0629.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:10:56'
  WHERE original_filename = '036A0630.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:10:59'
  WHERE original_filename = '036A0631.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:02'
  WHERE original_filename = '036A0632.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:17'
  WHERE original_filename = '036A0633.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:19'
  WHERE original_filename = '036A0634.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:22'
  WHERE original_filename = '036A0635.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:24'
  WHERE original_filename = '036A0636.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:27'
  WHERE original_filename = '036A0637.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:29'
  WHERE original_filename = '036A0638.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:33'
  WHERE original_filename = '036A0639.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:36'
  WHERE original_filename = '036A0640.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:39'
  WHERE original_filename = '036A0641.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:41'
  WHERE original_filename = '036A0642.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:11:43'
  WHERE original_filename = '036A0643.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:23:16'
  WHERE original_filename = '036A0644.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:23:19'
  WHERE original_filename = '036A0645.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:23:59'
  WHERE original_filename = '036A0646.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:02'
  WHERE original_filename = '036A0647.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:06'
  WHERE original_filename = '036A0648.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:11'
  WHERE original_filename = '036A0649.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:17'
  WHERE original_filename = '036A0650.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:20'
  WHERE original_filename = '036A0651.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:24'
  WHERE original_filename = '036A0652.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:27'
  WHERE original_filename = '036A0653.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:30'
  WHERE original_filename = '036A0654.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:33'
  WHERE original_filename = '036A0655.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:24:42'
  WHERE original_filename = '036A0656.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:20'
  WHERE original_filename = '036A0657.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:25'
  WHERE original_filename = '036A0658.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:30'
  WHERE original_filename = '036A0659.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:33'
  WHERE original_filename = '036A0660.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:49'
  WHERE original_filename = '036A0661.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:52'
  WHERE original_filename = '036A0662.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:25:58'
  WHERE original_filename = '036A0663.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:26:01'
  WHERE original_filename = '036A0664.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:26:07'
  WHERE original_filename = '036A0665.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:26:14'
  WHERE original_filename = '036A0666.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:26:19'
  WHERE original_filename = '036A0667.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:26:22'
  WHERE original_filename = '036A0668.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:10'
  WHERE original_filename = '036A0669.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:13'
  WHERE original_filename = '036A0670.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:17'
  WHERE original_filename = '036A0671.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:19'
  WHERE original_filename = '036A0672.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:23'
  WHERE original_filename = '036A0673.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:33'
  WHERE original_filename = '036A0674.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:38'
  WHERE original_filename = '036A0675.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:42'
  WHERE original_filename = '036A0676.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:46'
  WHERE original_filename = '036A0677.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:51'
  WHERE original_filename = '036A0678.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:27:55'
  WHERE original_filename = '036A0679.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:28:03'
  WHERE original_filename = '036A0680.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:28:36'
  WHERE original_filename = '036A0681.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:28:42'
  WHERE original_filename = '036A0682.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:28:47'
  WHERE original_filename = '036A0683.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:28:52'
  WHERE original_filename = '036A0684.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:28:57'
  WHERE original_filename = '036A0685.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:29:04'
  WHERE original_filename = '036A0686.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:29:08'
  WHERE original_filename = '036A0687.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:29:12'
  WHERE original_filename = '036A0688.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:29:15'
  WHERE original_filename = '036A0689.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:29:20'
  WHERE original_filename = '036A0690.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:31:59'
  WHERE original_filename = '036A0691.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:32:03'
  WHERE original_filename = '036A0692.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:32:10'
  WHERE original_filename = '036A0693.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:32:16'
  WHERE original_filename = '036A0694.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:32:24'
  WHERE original_filename = '036A0695.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:32:46'
  WHERE original_filename = '036A0696.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:32:52'
  WHERE original_filename = '036A0697.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:00'
  WHERE original_filename = '036A0698.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:03'
  WHERE original_filename = '036A0699.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:12'
  WHERE original_filename = '036A0700.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:34'
  WHERE original_filename = '036A0701.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:39'
  WHERE original_filename = '036A0702.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:45'
  WHERE original_filename = '036A0703.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:50'
  WHERE original_filename = '036A0704.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:33:56'
  WHERE original_filename = '036A0705.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:34:11'
  WHERE original_filename = '036A0706.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:34:16'
  WHERE original_filename = '036A0707.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:34:25'
  WHERE original_filename = '036A0708.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:34:32'
  WHERE original_filename = '036A0709.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:35:30'
  WHERE original_filename = '036A0710.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:39:26'
  WHERE original_filename = '036A0711.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:40:10'
  WHERE original_filename = '036A0712.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:47:07'
  WHERE original_filename = '036A0713.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 12:48:03'
  WHERE original_filename = '036A0714.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:46:42'
  WHERE original_filename = '036A7970.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:47:08'
  WHERE original_filename = '036A7972.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:48:04'
  WHERE original_filename = '036A7973.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:49:08'
  WHERE original_filename = '036A7974.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:49:27'
  WHERE original_filename = '036A7975.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:49:56'
  WHERE original_filename = '036A7976.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:50:12'
  WHERE original_filename = '036A7977.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:50:24'
  WHERE original_filename = '036A7978.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:50:38'
  WHERE original_filename = '036A7979.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:51:10'
  WHERE original_filename = '036A7980.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:51:43'
  WHERE original_filename = '036A7981.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:52:47'
  WHERE original_filename = '036A7982.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:52:58'
  WHERE original_filename = '036A7983.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:53:25'
  WHERE original_filename = '036A7984.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:53:30'
  WHERE original_filename = '036A7985.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:54:19'
  WHERE original_filename = '036A7986.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:56:13'
  WHERE original_filename = '036A7987.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:56:44'
  WHERE original_filename = '036A7988.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:56:49'
  WHERE original_filename = '036A7989.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:56:51'
  WHERE original_filename = '036A7990.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:56:58'
  WHERE original_filename = '036A7991.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:58:07'
  WHERE original_filename = '036A7993.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:58:19'
  WHERE original_filename = '036A7995.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:58:48'
  WHERE original_filename = '036A7996.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:58:51'
  WHERE original_filename = '036A7997.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:58:54'
  WHERE original_filename = '036A7998.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 13:58:58'
  WHERE original_filename = '036A7999.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:00:40'
  WHERE original_filename = '036A8000.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:01:17'
  WHERE original_filename = '036A8002.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:01:20'
  WHERE original_filename = '036A8003.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:02:03'
  WHERE original_filename = '036A8004.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:02:36'
  WHERE original_filename = '036A8005.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:02:47'
  WHERE original_filename = '036A8006.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:02:59'
  WHERE original_filename = '036A8007.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:03:04'
  WHERE original_filename = '036A8008.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:03:07'
  WHERE original_filename = '036A8009.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:03:16'
  WHERE original_filename = '036A8010.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:03:30'
  WHERE original_filename = '036A8011.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:04:01'
  WHERE original_filename = '036A8012.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:07:42'
  WHERE original_filename = '036A8013.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:07:47'
  WHERE original_filename = '036A8014.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:07:56'
  WHERE original_filename = '036A8015.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:45:59'
  WHERE original_filename = '036A8269.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:46:07'
  WHERE original_filename = '036A8270.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:46:41'
  WHERE original_filename = '036A8271.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:47:08'
  WHERE original_filename = '036A8272.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:47:13'
  WHERE original_filename = '036A8273.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:47:31'
  WHERE original_filename = '036A8274.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:47:54'
  WHERE original_filename = '036A8275.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:47:56'
  WHERE original_filename = '036A8276.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:47:59'
  WHERE original_filename = '036A8277.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:48:02'
  WHERE original_filename = '036A8278.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:52:14'
  WHERE original_filename = '036A8291.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:55:54'
  WHERE original_filename = '036A8292.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:02'
  WHERE original_filename = '036A8293.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:25'
  WHERE original_filename = '036A8294.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:27'
  WHERE original_filename = '036A8295.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:30'
  WHERE original_filename = '036A8296.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:48'
  WHERE original_filename = '036A8297.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:51'
  WHERE original_filename = '036A8298.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:56:57'
  WHERE original_filename = '036A8299.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:05'
  WHERE original_filename = '036A8301.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:12'
  WHERE original_filename = '036A8302.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:14'
  WHERE original_filename = '036A8303.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:16'
  WHERE original_filename = '036A8304.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:19'
  WHERE original_filename = '036A8305.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:21'
  WHERE original_filename = '036A8306.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:57:49'
  WHERE original_filename = '036A8307.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:59:00'
  WHERE original_filename = '036A8308.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:59:06'
  WHERE original_filename = '036A8309.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 07:59:27'
  WHERE original_filename = '036A8310.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:00:26'
  WHERE original_filename = '036A8311.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:00:28'
  WHERE original_filename = '036A8312.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:00:40'
  WHERE original_filename = '036A8313.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:01:01'
  WHERE original_filename = '036A8314.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:01:40'
  WHERE original_filename = '036A8315.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:04:42'
  WHERE original_filename = '036A8317.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:04:48'
  WHERE original_filename = '036A8318.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:05:31'
  WHERE original_filename = '036A8319.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:05:47'
  WHERE original_filename = '036A8320.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:05:49'
  WHERE original_filename = '036A8321.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:05:53'
  WHERE original_filename = '036A8322.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:06:12'
  WHERE original_filename = '036A8323.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:06:17'
  WHERE original_filename = '036A8324.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:06:41'
  WHERE original_filename = '036A8325.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:07:36'
  WHERE original_filename = '036A8326.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:11:20'
  WHERE original_filename = '036A8328.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:12:02'
  WHERE original_filename = '036A8329.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:13:06'
  WHERE original_filename = '036A8330.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:13:42'
  WHERE original_filename = '036A8331.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:13:45'
  WHERE original_filename = '036A8332.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:19'
  WHERE original_filename = '036A8333.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:28'
  WHERE original_filename = '036A8334.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:30'
  WHERE original_filename = '036A8335.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:32'
  WHERE original_filename = '036A8336.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:35'
  WHERE original_filename = '036A8337.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:37'
  WHERE original_filename = '036A8338.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:14:51'
  WHERE original_filename = '036A8339.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:15:03'
  WHERE original_filename = '036A8340.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:15:07'
  WHERE original_filename = '036A8341.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:12'
  WHERE original_filename = '036A8342.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:17'
  WHERE original_filename = '036A8343.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:25'
  WHERE original_filename = '036A8344.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:26'
  WHERE original_filename = '036A8345.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:28'
  WHERE original_filename = '036A8346.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:30'
  WHERE original_filename = '036A8347.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:32'
  WHERE original_filename = '036A8348.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:16:34'
  WHERE original_filename = '036A8349.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:22:48'
  WHERE original_filename = '036A8352.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:22:53'
  WHERE original_filename = '036A8353.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:22:55'
  WHERE original_filename = '036A8354.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:22:57'
  WHERE original_filename = '036A8355.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:02'
  WHERE original_filename = '036A8356.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:03'
  WHERE original_filename = '036A8357.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:06'
  WHERE original_filename = '036A8358.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:45'
  WHERE original_filename = '036A8359.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:47'
  WHERE original_filename = '036A8360.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:48'
  WHERE original_filename = '036A8361.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:23:59'
  WHERE original_filename = '036A8362.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:24:10'
  WHERE original_filename = '036A8363.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:25:29'
  WHERE original_filename = '036A8364.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:25:57'
  WHERE original_filename = '036A8365.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:25:59'
  WHERE original_filename = '036A8366.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:26:01'
  WHERE original_filename = '036A8367.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:26:03'
  WHERE original_filename = '036A8368.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:26:08'
  WHERE original_filename = '036A8369.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:27:06'
  WHERE original_filename = '036A8370.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:27:39'
  WHERE original_filename = '036A8371.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:31:53'
  WHERE original_filename = '036A8372.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:33:51'
  WHERE original_filename = '036A8373.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:16'
  WHERE original_filename = '036A8375.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:17'
  WHERE original_filename = '036A8376.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:19'
  WHERE original_filename = '036A8377.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:20'
  WHERE original_filename = '036A8378.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:22'
  WHERE original_filename = '036A8379.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:23'
  WHERE original_filename = '036A8380.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:24'
  WHERE original_filename = '036A8381.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:26'
  WHERE original_filename = '036A8382.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:28'
  WHERE original_filename = '036A8383.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:32'
  WHERE original_filename = '036A8384.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:35:54'
  WHERE original_filename = '036A8385.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:36:09'
  WHERE original_filename = '036A8386.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:36:13'
  WHERE original_filename = '036A8387.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:36:53'
  WHERE original_filename = '036A8388.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:37:03'
  WHERE original_filename = '036A8389.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:37:12'
  WHERE original_filename = '036A8390.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:37:16'
  WHERE original_filename = '036A8391.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:37:24'
  WHERE original_filename = '036A8392.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:39:00'
  WHERE original_filename = '036A8393.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:39:17'
  WHERE original_filename = '036A8394.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:39:50'
  WHERE original_filename = '036A8395.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:39:55'
  WHERE original_filename = '036A8396.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:40:02'
  WHERE original_filename = '036A8397.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:40:08'
  WHERE original_filename = '036A8398.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:41:44'
  WHERE original_filename = '036A8399.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:42:12'
  WHERE original_filename = '036A8400.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:42:24'
  WHERE original_filename = '036A8401.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:45:41'
  WHERE original_filename = '036A8407.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:45:55'
  WHERE original_filename = '036A8408.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:45:58'
  WHERE original_filename = '036A8409.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:46:01'
  WHERE original_filename = '036A8410.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:46:06'
  WHERE original_filename = '036A8411.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:46:07'
  WHERE original_filename = '036A8412.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:46:11'
  WHERE original_filename = '036A8413.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:47:07'
  WHERE original_filename = '036A8414.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:47:21'
  WHERE original_filename = '036A8415.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:52:13'
  WHERE original_filename = '036A8416.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:52:34'
  WHERE original_filename = '036A8417.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:52:43'
  WHERE original_filename = '036A8418.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:52:48'
  WHERE original_filename = '036A8419.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:53:44'
  WHERE original_filename = '036A8421.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:54:18'
  WHERE original_filename = '036A8422.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:54:42'
  WHERE original_filename = '036A8423.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:55:35'
  WHERE original_filename = '036A8424.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:57:44'
  WHERE original_filename = '036A8425.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:57:45'
  WHERE original_filename = '036A8426.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:57:46'
  WHERE original_filename = '036A8427.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:58:29'
  WHERE original_filename = '036A8429.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:01:18'
  WHERE original_filename = '036A8430.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:02:17'
  WHERE original_filename = '036A8431.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:02:18'
  WHERE original_filename = '036A8432.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:02:19'
  WHERE original_filename = '036A8433.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:02:20'
  WHERE original_filename = '036A8434.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:02:21'
  WHERE original_filename = '036A8435.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:02:49'
  WHERE original_filename = '036A8436.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:06:30'
  WHERE original_filename = '036A8438.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:06:38'
  WHERE original_filename = '036A8439.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:06:42'
  WHERE original_filename = '036A8440.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:10:19'
  WHERE original_filename = '036A8441.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:10:21'
  WHERE original_filename = '036A8442.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:10:22'
  WHERE original_filename = '036A8443.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:10:24'
  WHERE original_filename = '036A8444.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 09:10:26'
  WHERE original_filename = '036A8445.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 13:52:02'
  WHERE original_filename = '036A8583.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 13:52:07'
  WHERE original_filename = '036A8584.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 13:52:12'
  WHERE original_filename = '036A8585.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 13:52:16'
  WHERE original_filename = '036A8586.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 13:52:20'
  WHERE original_filename = '036A8587.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:21:32'
  WHERE original_filename = '036A8588.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:30:59'
  WHERE original_filename = '036A8589.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:31:02'
  WHERE original_filename = '036A8590.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:31:12'
  WHERE original_filename = '036A8591.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:31:19'
  WHERE original_filename = '036A8592.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:34:13'
  WHERE original_filename = '036A8594.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:37:46'
  WHERE original_filename = '036A8595.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:39:15'
  WHERE original_filename = '036A8596.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:39:24'
  WHERE original_filename = '036A8597.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:41:49'
  WHERE original_filename = '036A8598.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:43:18'
  WHERE original_filename = '036A8599.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:43:38'
  WHERE original_filename = '036A8600.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:43:56'
  WHERE original_filename = '036A8601.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:43:59'
  WHERE original_filename = '036A8602.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:44:06'
  WHERE original_filename = '036A8603.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:44:39'
  WHERE original_filename = '036A8604.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:45:43'
  WHERE original_filename = '036A8605.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:27'
  WHERE original_filename = '036A8606.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:29'
  WHERE original_filename = '036A8607.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:30'
  WHERE original_filename = '036A8608.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:33'
  WHERE original_filename = '036A8609.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:34'
  WHERE original_filename = '036A8610.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:35'
  WHERE original_filename = '036A8611.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:36'
  WHERE original_filename = '036A8612.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:38'
  WHERE original_filename = '036A8613.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:40'
  WHERE original_filename = '036A8614.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:50'
  WHERE original_filename = '036A8615.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:51'
  WHERE original_filename = '036A8616.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:52'
  WHERE original_filename = '036A8617.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:54'
  WHERE original_filename = '036A8618.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:46:59'
  WHERE original_filename = '036A8619.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:47:00'
  WHERE original_filename = '036A8620.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:47:01'
  WHERE original_filename = '036A8621.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:49:06'
  WHERE original_filename = '036A8622.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:58:35'
  WHERE original_filename = '036A8626.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:58:39'
  WHERE original_filename = '036A8627.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:58:40'
  WHERE original_filename = '036A8628.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:58:43'
  WHERE original_filename = '036A8629.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:58:57'
  WHERE original_filename = '036A8631.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:59:00'
  WHERE original_filename = '036A8632.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:59:20'
  WHERE original_filename = '036A8633.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 14:59:31'
  WHERE original_filename = '036A8634.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:23:26'
  WHERE original_filename = '036A8636.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:23:29'
  WHERE original_filename = '036A8637.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:52:56'
  WHERE original_filename = '036A8643.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:53:13'
  WHERE original_filename = '036A8644.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:53:48'
  WHERE original_filename = '036A8645.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:53:49'
  WHERE original_filename = '036A8646.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:53:51'
  WHERE original_filename = '036A8647.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:53:54'
  WHERE original_filename = '036A8648.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:54:02'
  WHERE original_filename = '036A8649.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:54:03'
  WHERE original_filename = '036A8650.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-23 15:54:18'
  WHERE original_filename = '036A8651.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:22:12'
  WHERE original_filename = '036A8660.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:22:16'
  WHERE original_filename = '036A8661.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:23:40'
  WHERE original_filename = '036A8662.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:23:56'
  WHERE original_filename = '036A8663.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:23:58'
  WHERE original_filename = '036A8664.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:23:59'
  WHERE original_filename = '036A8665.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:24:13'
  WHERE original_filename = '036A8666.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:24:20'
  WHERE original_filename = '036A8667.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:20'
  WHERE original_filename = '036A8668.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:25'
  WHERE original_filename = '036A8669.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:28'
  WHERE original_filename = '036A8670.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:31'
  WHERE original_filename = '036A8671.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:34'
  WHERE original_filename = '036A8672.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:38'
  WHERE original_filename = '036A8673.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:41'
  WHERE original_filename = '036A8674.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:34:44'
  WHERE original_filename = '036A8675.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:35:00'
  WHERE original_filename = '036A8676.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:35:02'
  WHERE original_filename = '036A8677.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:35:06'
  WHERE original_filename = '036A8678.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:35:08'
  WHERE original_filename = '036A8679.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:35:11'
  WHERE original_filename = '036A8680.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:42:24'
  WHERE original_filename = '036A8681.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:42:40'
  WHERE original_filename = '036A8682.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:42:43'
  WHERE original_filename = '036A8683.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:42:53'
  WHERE original_filename = '036A8684.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:44:13'
  WHERE original_filename = '036A8685.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:46:11'
  WHERE original_filename = '036A8686.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:53:26'
  WHERE original_filename = '036A8687.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:53:36'
  WHERE original_filename = '036A8688.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:53:39'
  WHERE original_filename = '036A8689.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:53:44'
  WHERE original_filename = '036A8690.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:53:47'
  WHERE original_filename = '036A8691.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:54:06'
  WHERE original_filename = '036A8692.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 14:54:33'
  WHERE original_filename = '036A8693.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:39'
  WHERE original_filename = '036A8694.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:41'
  WHERE original_filename = '036A8695.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:44'
  WHERE original_filename = '036A8696.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:48'
  WHERE original_filename = '036A8697.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:52'
  WHERE original_filename = '036A8698.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:54'
  WHERE original_filename = '036A8699.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:56'
  WHERE original_filename = '036A8700.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:06:59'
  WHERE original_filename = '036A8701.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:07:04'
  WHERE original_filename = '036A8702.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:07:06'
  WHERE original_filename = '036A8703.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:07:08'
  WHERE original_filename = '036A8704.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:07:10'
  WHERE original_filename = '036A8705.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:07:17'
  WHERE original_filename = '036A8706.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:07:23'
  WHERE original_filename = '036A8707.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:50:33'
  WHERE original_filename = '036A8708.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:50:41'
  WHERE original_filename = '036A8709.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:50:43'
  WHERE original_filename = '036A8710.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:50:46'
  WHERE original_filename = '036A8711.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:50:47'
  WHERE original_filename = '036A8712.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:50:49'
  WHERE original_filename = '036A8713.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:52:05'
  WHERE original_filename = '036A8714.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:52:07'
  WHERE original_filename = '036A8715.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:52:09'
  WHERE original_filename = '036A8716.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:52:13'
  WHERE original_filename = '036A8717.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:52:16'
  WHERE original_filename = '036A8718.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 15:52:19'
  WHERE original_filename = '036A8719.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:24'
  WHERE original_filename = '036A8720.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:25'
  WHERE original_filename = '036A8721.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:33'
  WHERE original_filename = '036A8722.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:34'
  WHERE original_filename = '036A8723.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:38'
  WHERE original_filename = '036A8724.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:39'
  WHERE original_filename = '036A8725.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:42'
  WHERE original_filename = '036A8726.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:43'
  WHERE original_filename = '036A8727.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:46'
  WHERE original_filename = '036A8728.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:48'
  WHERE original_filename = '036A8729.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:50'
  WHERE original_filename = '036A8730.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:52'
  WHERE original_filename = '036A8731.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:54'
  WHERE original_filename = '036A8732.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:56'
  WHERE original_filename = '036A8733.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:09:59'
  WHERE original_filename = '036A8734.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:00'
  WHERE original_filename = '036A8735.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:03'
  WHERE original_filename = '036A8736.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:05'
  WHERE original_filename = '036A8737.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:06'
  WHERE original_filename = '036A8738.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:08'
  WHERE original_filename = '036A8739.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:10'
  WHERE original_filename = '036A8740.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:11'
  WHERE original_filename = '036A8741.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:13'
  WHERE original_filename = '036A8742.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:15'
  WHERE original_filename = '036A8743.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:29'
  WHERE original_filename = '036A8744.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:30'
  WHERE original_filename = '036A8745.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:31'
  WHERE original_filename = '036A8746.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:33'
  WHERE original_filename = '036A8747.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:35'
  WHERE original_filename = '036A8748.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:10:41'
  WHERE original_filename = '036A8749.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:28:00'
  WHERE original_filename = '036A8750.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:45:08'
  WHERE original_filename = '036A8755.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:45:15'
  WHERE original_filename = '036A8756.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:45:17'
  WHERE original_filename = '036A8757.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:45:18'
  WHERE original_filename = '036A8758.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:45:41'
  WHERE original_filename = '036A8759.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-28 16:45:45'
  WHERE original_filename = '036A8760.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:55:01'
  WHERE original_filename = '036A8770.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:55:03'
  WHERE original_filename = '036A8771.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:55:06'
  WHERE original_filename = '036A8772.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:55:09'
  WHERE original_filename = '036A8773.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:55:55'
  WHERE original_filename = '036A8774.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:55:57'
  WHERE original_filename = '036A8775.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:00'
  WHERE original_filename = '036A8776.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:03'
  WHERE original_filename = '036A8777.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:07'
  WHERE original_filename = '036A8778.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:09'
  WHERE original_filename = '036A8779.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:12'
  WHERE original_filename = '036A8780.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:16'
  WHERE original_filename = '036A8781.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:19'
  WHERE original_filename = '036A8782.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:22'
  WHERE original_filename = '036A8783.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:29'
  WHERE original_filename = '036A8784.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:31'
  WHERE original_filename = '036A8785.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:33'
  WHERE original_filename = '036A8786.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:34'
  WHERE original_filename = '036A8787.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:36'
  WHERE original_filename = '036A8788.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:40'
  WHERE original_filename = '036A8789.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:46'
  WHERE original_filename = '036A8790.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:48'
  WHERE original_filename = '036A8791.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:50'
  WHERE original_filename = '036A8792.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:52'
  WHERE original_filename = '036A8793.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:54'
  WHERE original_filename = '036A8794.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:56:56'
  WHERE original_filename = '036A8795.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:02'
  WHERE original_filename = '036A8796.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:04'
  WHERE original_filename = '036A8797.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:06'
  WHERE original_filename = '036A8798.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:13'
  WHERE original_filename = '036A8799.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:14'
  WHERE original_filename = '036A8800.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:16'
  WHERE original_filename = '036A8801.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:21'
  WHERE original_filename = '036A8802.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:32'
  WHERE original_filename = '036A8803.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:34'
  WHERE original_filename = '036A8804.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:38'
  WHERE original_filename = '036A8805.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:40'
  WHERE original_filename = '036A8806.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:43'
  WHERE original_filename = '036A8807.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:45'
  WHERE original_filename = '036A8808.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:49'
  WHERE original_filename = '036A8809.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:55'
  WHERE original_filename = '036A8810.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:57:57'
  WHERE original_filename = '036A8811.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:02'
  WHERE original_filename = '036A8812.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:04'
  WHERE original_filename = '036A8813.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:16'
  WHERE original_filename = '036A8814.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:18'
  WHERE original_filename = '036A8815.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:35'
  WHERE original_filename = '036A8816.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:37'
  WHERE original_filename = '036A8817.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:43'
  WHERE original_filename = '036A8818.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:45'
  WHERE original_filename = '036A8819.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:51'
  WHERE original_filename = '036A8820.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:53'
  WHERE original_filename = '036A8821.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:58:55'
  WHERE original_filename = '036A8822.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:01'
  WHERE original_filename = '036A8823.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:04'
  WHERE original_filename = '036A8824.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:07'
  WHERE original_filename = '036A8825.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:12'
  WHERE original_filename = '036A8826.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:14'
  WHERE original_filename = '036A8827.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:17'
  WHERE original_filename = '036A8828.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:22'
  WHERE original_filename = '036A8829.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:26'
  WHERE original_filename = '036A8830.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:29'
  WHERE original_filename = '036A8831.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:32'
  WHERE original_filename = '036A8832.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:34'
  WHERE original_filename = '036A8833.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:37'
  WHERE original_filename = '036A8834.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:43'
  WHERE original_filename = '036A8835.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:45'
  WHERE original_filename = '036A8836.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:47'
  WHERE original_filename = '036A8837.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 15:59:49'
  WHERE original_filename = '036A8838.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:14'
  WHERE original_filename = '036A8839.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:15'
  WHERE original_filename = '036A8840.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:18'
  WHERE original_filename = '036A8841.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:20'
  WHERE original_filename = '036A8842.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:22'
  WHERE original_filename = '036A8843.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:24'
  WHERE original_filename = '036A8844.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:26'
  WHERE original_filename = '036A8845.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:29'
  WHERE original_filename = '036A8846.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:30'
  WHERE original_filename = '036A8847.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:32'
  WHERE original_filename = '036A8848.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:49'
  WHERE original_filename = '036A8849.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:51'
  WHERE original_filename = '036A8850.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:00:53'
  WHERE original_filename = '036A8851.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:30:57'
  WHERE original_filename = '036A8913.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:30:58'
  WHERE original_filename = '036A8914.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:30:59'
  WHERE original_filename = '036A8915.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:05'
  WHERE original_filename = '036A8916.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:06'
  WHERE original_filename = '036A8917.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:07'
  WHERE original_filename = '036A8918.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:10'
  WHERE original_filename = '036A8919.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:13'
  WHERE original_filename = '036A8920.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:16'
  WHERE original_filename = '036A8921.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:18'
  WHERE original_filename = '036A8922.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:21'
  WHERE original_filename = '036A8923.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:23'
  WHERE original_filename = '036A8924.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:28'
  WHERE original_filename = '036A8925.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:34'
  WHERE original_filename = '036A8926.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:42'
  WHERE original_filename = '036A8927.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:48'
  WHERE original_filename = '036A8928.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:50'
  WHERE original_filename = '036A8929.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:52'
  WHERE original_filename = '036A8930.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:54'
  WHERE original_filename = '036A8931.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:56'
  WHERE original_filename = '036A8932.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:58'
  WHERE original_filename = '036A8933.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:31:59'
  WHERE original_filename = '036A8934.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:03'
  WHERE original_filename = '036A8935.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:05'
  WHERE original_filename = '036A8936.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:10'
  WHERE original_filename = '036A8937.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:23'
  WHERE original_filename = '036A8938.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:24'
  WHERE original_filename = '036A8939.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:25'
  WHERE original_filename = '036A8940.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:26'
  WHERE original_filename = '036A8941.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:28'
  WHERE original_filename = '036A8942.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:29'
  WHERE original_filename = '036A8943.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:31'
  WHERE original_filename = '036A8944.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:40'
  WHERE original_filename = '036A8945.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:41'
  WHERE original_filename = '036A8946.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:43'
  WHERE original_filename = '036A8947.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:44'
  WHERE original_filename = '036A8948.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:45'
  WHERE original_filename = '036A8949.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:32:49'
  WHERE original_filename = '036A8950.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:45:38'
  WHERE original_filename = '036A8953.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:45:50'
  WHERE original_filename = '036A8954.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:45:56'
  WHERE original_filename = '036A8955.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:46:18'
  WHERE original_filename = '036A8956.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:46:30'
  WHERE original_filename = '036A8957.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:46:33'
  WHERE original_filename = '036A8958.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:46:37'
  WHERE original_filename = '036A8959.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:46:41'
  WHERE original_filename = '036A8960.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:46:44'
  WHERE original_filename = '036A8961.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:47:04'
  WHERE original_filename = '036A8962.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:47:07'
  WHERE original_filename = '036A8963.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:47:11'
  WHERE original_filename = '036A8964.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:47:22'
  WHERE original_filename = '036A8965.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:48:56'
  WHERE original_filename = '036A8968.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:48:58'
  WHERE original_filename = '036A8969.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:49:00'
  WHERE original_filename = '036A8970.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:49:02'
  WHERE original_filename = '036A8971.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:49:05'
  WHERE original_filename = '036A8972.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:49:08'
  WHERE original_filename = '036A8973.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:49:40'
  WHERE original_filename = '036A8974.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:52:15'
  WHERE original_filename = '036A8975.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:56:15'
  WHERE original_filename = '036A8976.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:56:40'
  WHERE original_filename = '036A8977.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 16:56:46'
  WHERE original_filename = '036A8978.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:47'
  WHERE original_filename = '036A8979.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:48'
  WHERE original_filename = '036A8980.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:49'
  WHERE original_filename = '036A8981.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:51'
  WHERE original_filename = '036A8982.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:52'
  WHERE original_filename = '036A8983.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:53'
  WHERE original_filename = '036A8984.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:54'
  WHERE original_filename = '036A8985.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:56'
  WHERE original_filename = '036A8986.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:06:57'
  WHERE original_filename = '036A8987.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:09'
  WHERE original_filename = '036A8988.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:10'
  WHERE original_filename = '036A8989.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:11'
  WHERE original_filename = '036A8990.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:13'
  WHERE original_filename = '036A8991.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:14'
  WHERE original_filename = '036A8992.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:15'
  WHERE original_filename = '036A8993.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:17'
  WHERE original_filename = '036A8994.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:18'
  WHERE original_filename = '036A8995.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:20'
  WHERE original_filename = '036A8996.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:21'
  WHERE original_filename = '036A8997.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:23'
  WHERE original_filename = '036A8998.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:24'
  WHERE original_filename = '036A8999.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:15:49'
  WHERE original_filename = '036A9000.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:20:57'
  WHERE original_filename = '036A9001.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:20:58'
  WHERE original_filename = '036A9002.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:21:00'
  WHERE original_filename = '036A9003.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:21:02'
  WHERE original_filename = '036A9004.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:21:03'
  WHERE original_filename = '036A9005.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:21:06'
  WHERE original_filename = '036A9006.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-14 15:57:56'
  WHERE original_filename = '036A9196 - 036A9206.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-14 15:58:23'
  WHERE original_filename = '036A9206 - 036A9216.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-14 15:59:09'
  WHERE original_filename = '036A9219 - 036A9224.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-14 16:23:13'
  WHERE original_filename = '036A9261 - 036A9270.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:32'
  WHERE original_filename = '036A9631.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:33'
  WHERE original_filename = '036A9632.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:35'
  WHERE original_filename = '036A9633.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:36'
  WHERE original_filename = '036A9634.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:38'
  WHERE original_filename = '036A9635.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:40'
  WHERE original_filename = '036A9636.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:42'
  WHERE original_filename = '036A9637.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:44'
  WHERE original_filename = '036A9638.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:46'
  WHERE original_filename = '036A9639.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:48'
  WHERE original_filename = '036A9640.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:20:50'
  WHERE original_filename = '036A9641.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:21:05'
  WHERE original_filename = '036A9642.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:21:16'
  WHERE original_filename = '036A9643.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:10'
  WHERE original_filename = '036A9644.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:12'
  WHERE original_filename = '036A9645.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:22'
  WHERE original_filename = '036A9646.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:24'
  WHERE original_filename = '036A9647.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:27'
  WHERE original_filename = '036A9648.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:29'
  WHERE original_filename = '036A9649.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:30'
  WHERE original_filename = '036A9650.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:32'
  WHERE original_filename = '036A9651.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:34'
  WHERE original_filename = '036A9652.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:36'
  WHERE original_filename = '036A9653.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:37'
  WHERE original_filename = '036A9654.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:39'
  WHERE original_filename = '036A9655.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:26:40'
  WHERE original_filename = '036A9656.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:33:24'
  WHERE original_filename = '036A9657.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:33:52'
  WHERE original_filename = '036A9658.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:34:15'
  WHERE original_filename = '036A9659.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:34:17'
  WHERE original_filename = '036A9660.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:34:41'
  WHERE original_filename = '036A9661.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:35:34'
  WHERE original_filename = '036A9662.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:37:25'
  WHERE original_filename = '036A9663.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:37:38'
  WHERE original_filename = '036A9664.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:37:58'
  WHERE original_filename = '036A9665.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:38:05'
  WHERE original_filename = '036A9666.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:39:14'
  WHERE original_filename = '036A9667.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:40:11'
  WHERE original_filename = '036A9668.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:40:45'
  WHERE original_filename = '036A9669.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:40:54'
  WHERE original_filename = '036A9670.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:41:16'
  WHERE original_filename = '036A9671.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:41:17'
  WHERE original_filename = '036A9672.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:41:18'
  WHERE original_filename = '036A9673.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:42:21'
  WHERE original_filename = '036A9674.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:42:55'
  WHERE original_filename = '036A9675.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:44:33'
  WHERE original_filename = '036A9676.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:44:35'
  WHERE original_filename = '036A9677.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:44:37'
  WHERE original_filename = '036A9678.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:44:42'
  WHERE original_filename = '036A9679.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:44:51'
  WHERE original_filename = '036A9680.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:44:55'
  WHERE original_filename = '036A9681.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:47:53'
  WHERE original_filename = '036A9682.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:51:23'
  WHERE original_filename = '036A9683.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:51:32'
  WHERE original_filename = '036A9684.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:51:44'
  WHERE original_filename = '036A9685.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:52:00'
  WHERE original_filename = '036A9686.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:52:22'
  WHERE original_filename = '036A9687.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:52:27'
  WHERE original_filename = '036A9688.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:52:41'
  WHERE original_filename = '036A9689.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:53:19'
  WHERE original_filename = '036A9690.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:53:24'
  WHERE original_filename = '036A9691.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:53:32'
  WHERE original_filename = '036A9692.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:53:53'
  WHERE original_filename = '036A9693.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:54:02'
  WHERE original_filename = '036A9694.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:55:13'
  WHERE original_filename = '036A9695.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:55:23'
  WHERE original_filename = '036A9696.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:55:36'
  WHERE original_filename = '036A9697.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:55:44'
  WHERE original_filename = '036A9698.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:55:57'
  WHERE original_filename = '036A9699.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 16:56:24'
  WHERE original_filename = '036A9700.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:04'
  WHERE original_filename = '036A9739.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:06'
  WHERE original_filename = '036A9740.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:08'
  WHERE original_filename = '036A9741.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:09'
  WHERE original_filename = '036A9742.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:11'
  WHERE original_filename = '036A9743.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:12'
  WHERE original_filename = '036A9744.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:14'
  WHERE original_filename = '036A9745.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:15'
  WHERE original_filename = '036A9746.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:17'
  WHERE original_filename = '036A9747.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:18'
  WHERE original_filename = '036A9748.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:20'
  WHERE original_filename = '036A9749.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:21'
  WHERE original_filename = '036A9750.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:23'
  WHERE original_filename = '036A9751.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:24'
  WHERE original_filename = '036A9752.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:26'
  WHERE original_filename = '036A9753.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:28'
  WHERE original_filename = '036A9754.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:29'
  WHERE original_filename = '036A9755.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:32'
  WHERE original_filename = '036A9756.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:10:34'
  WHERE original_filename = '036A9757.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:11:53'
  WHERE original_filename = '036A9758.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:12:12'
  WHERE original_filename = '036A9759.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:12:20'
  WHERE original_filename = '036A9760.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:13:05'
  WHERE original_filename = '036A9761.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:13:09'
  WHERE original_filename = '036A9762.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:13:29'
  WHERE original_filename = '036A9763.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:13:39'
  WHERE original_filename = '036A9764.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:14:17'
  WHERE original_filename = '036A9765.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:14:31'
  WHERE original_filename = '036A9766.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:14:38'
  WHERE original_filename = '036A9767.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:14:56'
  WHERE original_filename = '036A9768.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:15:02'
  WHERE original_filename = '036A9769.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:04'
  WHERE original_filename = '036A9770.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:05'
  WHERE original_filename = '036A9771.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:08'
  WHERE original_filename = '036A9772.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:09'
  WHERE original_filename = '036A9773.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:12'
  WHERE original_filename = '036A9774.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:14'
  WHERE original_filename = '036A9775.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:16'
  WHERE original_filename = '036A9776.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:20'
  WHERE original_filename = '036A9777.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:24'
  WHERE original_filename = '036A9778.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:16:50'
  WHERE original_filename = '036A9779.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:17:00'
  WHERE original_filename = '036A9780.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:17:05'
  WHERE original_filename = '036A9781.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:17:11'
  WHERE original_filename = '036A9782.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:17:39'
  WHERE original_filename = '036A9783.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:18:27'
  WHERE original_filename = '036A9784.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:20:08'
  WHERE original_filename = '036A9785.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:25:25'
  WHERE original_filename = '036A9786.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-21 17:26:39'
  WHERE original_filename = '036A9787.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:32:30'
  WHERE original_filename = '036A9792.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:32:32'
  WHERE original_filename = '036A9793.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:32:34'
  WHERE original_filename = '036A9794.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:32:36'
  WHERE original_filename = '036A9795.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:32:38'
  WHERE original_filename = '036A9796.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:33:30'
  WHERE original_filename = '036A9797.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:33:36'
  WHERE original_filename = '036A9798.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:33:37'
  WHERE original_filename = '036A9799.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:33:38'
  WHERE original_filename = '036A9800.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:35:48'
  WHERE original_filename = '036A9809.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:36:00'
  WHERE original_filename = '036A9810.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:36:39'
  WHERE original_filename = '036A9811.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:37:10'
  WHERE original_filename = '036A9812.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:37:34'
  WHERE original_filename = '036A9813.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:37:58'
  WHERE original_filename = '036A9814.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:38:15'
  WHERE original_filename = '036A9815.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:38:50'
  WHERE original_filename = '036A9816.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:40:15'
  WHERE original_filename = '036A9817.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:40:16'
  WHERE original_filename = '036A9818.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:40:28'
  WHERE original_filename = '036A9819.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:40:34'
  WHERE original_filename = '036A9820.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:40:39'
  WHERE original_filename = '036A9821.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:40:52'
  WHERE original_filename = '036A9822.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:41:21'
  WHERE original_filename = '036A9823.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:41:31'
  WHERE original_filename = '036A9824.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:42:29'
  WHERE original_filename = '036A9825.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:42:56'
  WHERE original_filename = '036A9826.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:43:11'
  WHERE original_filename = '036A9827.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:43:39'
  WHERE original_filename = '036A9828.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:44:23'
  WHERE original_filename = '036A9829.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:44:25'
  WHERE original_filename = '036A9830.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:44:28'
  WHERE original_filename = '036A9831.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:44:55'
  WHERE original_filename = '036A9832.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:45:16'
  WHERE original_filename = '036A9833.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:46:12'
  WHERE original_filename = '036A9834.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:46:19'
  WHERE original_filename = '036A9835.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:48:59'
  WHERE original_filename = '036A9836.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:01'
  WHERE original_filename = '036A9837.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:04'
  WHERE original_filename = '036A9838.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:11'
  WHERE original_filename = '036A9839.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:12'
  WHERE original_filename = '036A9840.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:13'
  WHERE original_filename = '036A9841.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:15'
  WHERE original_filename = '036A9842.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:17'
  WHERE original_filename = '036A9843.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:18'
  WHERE original_filename = '036A9844.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:20'
  WHERE original_filename = '036A9845.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:23'
  WHERE original_filename = '036A9846.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:49:26'
  WHERE original_filename = '036A9847.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:50:09'
  WHERE original_filename = '036A9848.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:50:40'
  WHERE original_filename = '036A9849.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:51:02'
  WHERE original_filename = '036A9850.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:51:59'
  WHERE original_filename = '036A9851.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:52:32'
  WHERE original_filename = '036A9852.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:53:22'
  WHERE original_filename = '036A9853.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:54:38'
  WHERE original_filename = '036A9854.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:54:47'
  WHERE original_filename = '036A9855.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:54:58'
  WHERE original_filename = '036A9856.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:56:14'
  WHERE original_filename = '036A9857.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:56:33'
  WHERE original_filename = '036A9858.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:56:40'
  WHERE original_filename = '036A9859.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:57:14'
  WHERE original_filename = '036A9860.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:57:48'
  WHERE original_filename = '036A9861.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:57:51'
  WHERE original_filename = '036A9862.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:59:02'
  WHERE original_filename = '036A9863.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 13:59:20'
  WHERE original_filename = '036A9864.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:00:08'
  WHERE original_filename = '036A9865.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:01:37'
  WHERE original_filename = '036A9866.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:02:16'
  WHERE original_filename = '036A9867.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:03:05'
  WHERE original_filename = '036A9868.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:25:49'
  WHERE original_filename = '036A9869.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:25:52'
  WHERE original_filename = '036A9870.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:25:56'
  WHERE original_filename = '036A9871.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:26:01'
  WHERE original_filename = '036A9872.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 14:26:20'
  WHERE original_filename = '036A9873.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:32'
  WHERE original_filename = '036A9874.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:34'
  WHERE original_filename = '036A9875.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:36'
  WHERE original_filename = '036A9876.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:38'
  WHERE original_filename = '036A9877.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:40'
  WHERE original_filename = '036A9878.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:43'
  WHERE original_filename = '036A9879.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:47'
  WHERE original_filename = '036A9880.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:52'
  WHERE original_filename = '036A9881.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:00:57'
  WHERE original_filename = '036A9882.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:01:23'
  WHERE original_filename = '036A9883.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:03:47'
  WHERE original_filename = '036A9884.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:03:48'
  WHERE original_filename = '036A9885.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:03:49'
  WHERE original_filename = '036A9886.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:03:51'
  WHERE original_filename = '036A9887.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:04:52'
  WHERE original_filename = '036A9888.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:04:54'
  WHERE original_filename = '036A9889.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-22 17:04:56'
  WHERE original_filename = '036A9890.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:12:54'
  WHERE original_filename = '036A9891.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:14:54'
  WHERE original_filename = '036A9907.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:15:04'
  WHERE original_filename = '036A9908.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:15:08'
  WHERE original_filename = '036A9909.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:15:11'
  WHERE original_filename = '036A9910.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:15:21'
  WHERE original_filename = '036A9911.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:15:50'
  WHERE original_filename = '036A9912.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:16:15'
  WHERE original_filename = '036A9913.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:16:24'
  WHERE original_filename = '036A9914.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:05'
  WHERE original_filename = '036A9915.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:07'
  WHERE original_filename = '036A9916.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:09'
  WHERE original_filename = '036A9917.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:11'
  WHERE original_filename = '036A9918.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:12'
  WHERE original_filename = '036A9919.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:15'
  WHERE original_filename = '036A9920.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:16'
  WHERE original_filename = '036A9921.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:18'
  WHERE original_filename = '036A9922.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:20'
  WHERE original_filename = '036A9923.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:22'
  WHERE original_filename = '036A9924.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:23'
  WHERE original_filename = '036A9925.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:25'
  WHERE original_filename = '036A9926.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:28'
  WHERE original_filename = '036A9927.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:31'
  WHERE original_filename = '036A9928.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:33'
  WHERE original_filename = '036A9929.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:35'
  WHERE original_filename = '036A9930.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:37'
  WHERE original_filename = '036A9931.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:39'
  WHERE original_filename = '036A9932.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:41'
  WHERE original_filename = '036A9933.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:43'
  WHERE original_filename = '036A9934.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:45'
  WHERE original_filename = '036A9935.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:48'
  WHERE original_filename = '036A9936.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:50'
  WHERE original_filename = '036A9937.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:19:53'
  WHERE original_filename = '036A9938.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:23:53'
  WHERE original_filename = '036A9939.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:23:59'
  WHERE original_filename = '036A9940.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:24:14'
  WHERE original_filename = '036A9941.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:27:02'
  WHERE original_filename = '036A9942.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:27:23'
  WHERE original_filename = '036A9943.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:29:25'
  WHERE original_filename = '036A9945.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:29:39'
  WHERE original_filename = '036A9946.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:31:31'
  WHERE original_filename = '036A9947.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:31:50'
  WHERE original_filename = '036A9948.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:32:35'
  WHERE original_filename = '036A9949.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:32:52'
  WHERE original_filename = '036A9950.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:35:08'
  WHERE original_filename = '036A9951.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:35:40'
  WHERE original_filename = '036A9952.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:36:48'
  WHERE original_filename = '036A9953.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:36:52'
  WHERE original_filename = '036A9954.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:36:56'
  WHERE original_filename = '036A9955.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:37:45'
  WHERE original_filename = '036A9956.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:17'
  WHERE original_filename = '036A9958.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:19'
  WHERE original_filename = '036A9959.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:21'
  WHERE original_filename = '036A9960.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:22'
  WHERE original_filename = '036A9961.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:25'
  WHERE original_filename = '036A9962.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:35'
  WHERE original_filename = '036A9963.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:37'
  WHERE original_filename = '036A9964.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:39:49'
  WHERE original_filename = '036A9965.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:40:07'
  WHERE original_filename = '036A9966.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:41:21'
  WHERE original_filename = '036A9967.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:43:10'
  WHERE original_filename = '036A9968.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:43:22'
  WHERE original_filename = '036A9969.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:43:38'
  WHERE original_filename = '036A9970.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:43:58'
  WHERE original_filename = '036A9971.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:44:07'
  WHERE original_filename = '036A9972.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:46:56'
  WHERE original_filename = '036A9973.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:46:59'
  WHERE original_filename = '036A9974.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:01'
  WHERE original_filename = '036A9975.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:04'
  WHERE original_filename = '036A9976.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:06'
  WHERE original_filename = '036A9977.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:08'
  WHERE original_filename = '036A9978.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:16'
  WHERE original_filename = '036A9979.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:18'
  WHERE original_filename = '036A9980.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:20'
  WHERE original_filename = '036A9981.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:21'
  WHERE original_filename = '036A9982.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:23'
  WHERE original_filename = '036A9983.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:25'
  WHERE original_filename = '036A9984.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:47:50'
  WHERE original_filename = '036A9985.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:48:50'
  WHERE original_filename = '036A9986.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:49:31'
  WHERE original_filename = '036A9987.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:49:42'
  WHERE original_filename = '036A9988.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:50:12'
  WHERE original_filename = '036A9989.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:22'
  WHERE original_filename = '036A9990.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:30'
  WHERE original_filename = '036A9991.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:34'
  WHERE original_filename = '036A9992.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:37'
  WHERE original_filename = '036A9993.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:41'
  WHERE original_filename = '036A9994.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:44'
  WHERE original_filename = '036A9995.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:49'
  WHERE original_filename = '036A9996.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:52:55'
  WHERE original_filename = '036A9997.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:53:01'
  WHERE original_filename = '036A9998.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:53:04'
  WHERE original_filename = '036A9999.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:25:33'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0715.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:25:51'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0716.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:26:01'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0717.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:26:04'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0718.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:26:09'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0719.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:26:59'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0720.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:27:36'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0721.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:27:41'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0722.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:27:44'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0723.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:27:46'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0724.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:27:49'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0725.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:28:15'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0726.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:29:37'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0727.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:30:50'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0728.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:31:45'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0729.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:31:56'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0730.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:32:18'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0731.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:32:48'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0732.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:33:02'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0733.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:33:41'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0734.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:34:29'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0735.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:37:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0737.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:37:52'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0738.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:38:56'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0739.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:39:04'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0740.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:39:18'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0741.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:40:04'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0742.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:40:15'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0743.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:40:58'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0744.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:41:18'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0745.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:41:20'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0746.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:41:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0747.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:42:06'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0748.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:43:12'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0749.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:43:35'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0750.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:43:52'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0751.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:44:19'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0753.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:44:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0754.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:47:06'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0755.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:47:52'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0756.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:48:41'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0758.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:48:51'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0759.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:55:30'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0760.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:55:34'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0761.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:55:48'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0763.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:55:55'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0764.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:56:02'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0765.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:56:05'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0766.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:56:14'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0767.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:56:23'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0768.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:56:54'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0769.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:57:22'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0770.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:57:32'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0771.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:57:38'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0772.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:57:49'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0773.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:58:30'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0775.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:59:18'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0777.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 10:59:33'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0778.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:01:07'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0779.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:01:27'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0780.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:01:31'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0781.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:02:12'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0782.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:02:29'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0783.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:02:44'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0784.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:02:55'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0785.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:03:01'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0786.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:03:09'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0787.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:03:42'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0788.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:03:44'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0789.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:03:54'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0790.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:03:57'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0791.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:04:02'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0792.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:04:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0793.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:04:32'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0794.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:04:36'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0795.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:05:02'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0796.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:05:20'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0797.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:05:47'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0798.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:06:05'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0799.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:06:14'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0800.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:06:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0801.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:08:52'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0802.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:08:53'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0803.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:09:23'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0804.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:09:33'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0805.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:12:10'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0806.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:13:48'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0807.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 11:16:13'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0808.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:10:57'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0819---2026-03-28_100EOS5D_036A0823.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:11:41'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0824---2026-03-28_100EOS5D_036A0829.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:12:27'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0830.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:12:48'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0831.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:19:03'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0832---2026-03-28_100EOS5D_036A0836.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:19:50'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0837---2026-03-28_100EOS5D_036A0842.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:22:03'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0843---2026-03-28_100EOS5D_036A0848.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:22:50'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0849.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:22:53'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0850.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:22:55'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0851.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:23:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0852.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:23:13'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0853.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:23:15'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0854.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:23:17'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0855---2026-03-28_100EOS5D_036A0863.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:24:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0864---2026-03-28_100EOS5D_036A0879.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:25:01'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0880.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:25:03'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0881.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:25:42'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0882.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:34:31'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0883.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:35:53'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0884.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:41:42'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0885---2026-03-28_100EOS5D_036A0889.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:44:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0890---2026-03-28_100EOS5D_036A0894.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:44:48'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0896.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:44:50'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0897.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:44:53'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0898.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:44:55'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0899.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:44:59'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0900.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:01'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0901.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:03'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0902.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:06'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0903.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:08'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0904.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:09'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0905.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0906.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:13'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0907.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:16'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0908.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:18'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0909.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:22'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0910.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0911.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:45:37'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0912.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:48:10'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0913.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:48:31'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0914---2026-03-28_100EOS5D_036A0921.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:48:56'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0922.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:49:53'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0923---2026-03-28_100EOS5D_036A0927.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:50:10'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0928---2026-03-28_100EOS5D_036A0949.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:51:17'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0950.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0951.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:12'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0952.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:14'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0953.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:16'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0954.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:17'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0955.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:19'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0956.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:21'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0957.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:23'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0958.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0959.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:26'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0960.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:28'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0961.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:30'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0962.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:32'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0963.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:35'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0964.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:36'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0965.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:52:45'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0966.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:55:17'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0967.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:55:57'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0968.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:57:34'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0969.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:57:39'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0970.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:58:40'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0971---2026-03-28_100EOS5D_036A0978.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:59:46'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0979.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 12:59:54'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0980.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:00:35'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0981.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:10:05'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0982.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:11:07'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0983.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:11:31'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0984.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:13:42'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0985.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:13:50'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0986.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:17:53'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0987.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:18'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0988.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:19'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0989.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:21'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0990.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0991.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:26'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0992.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:28'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0993.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:30'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0994.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:34'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0995.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:40'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0996.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:18:42'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0997.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:00'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0998.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:02'
  WHERE original_filename = '2026-03-28_100EOS5D_036A0999.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:04'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1000.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:06'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1001.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:07'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1002.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:09'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1003.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:11'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1004.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:12'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1005.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:14'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1006.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:16'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1007.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:17'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1008.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:19'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1009.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:22'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1010.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:24'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1011.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:25'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1012.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:30:27'
  WHERE original_filename = '2026-03-28_100EOS5D_036A1013.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:55:20'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1014.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:55:37'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1015.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:55:47'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1016.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:56:35'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1017.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:56:44'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1018.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:56:49'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1019.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:58:52'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1020.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:58:58'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1021.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 13:59:08'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1022.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:19:31'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1036.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:19:35'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1037.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:19:47'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1038.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:20:43'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1039.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:30:04'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1041.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:30:09'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1042.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:30:24'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1043.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:30:28'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1044.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:30:31'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1045.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:30:40'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1046.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:35:21'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1047.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:35:40'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1048.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:37:54'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1049.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:38:23'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1050.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:38:43'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1051.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 15:52:22'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1404.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 15:52:39'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1405.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 15:53:02'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1409.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 15:56:19'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1410.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:16:21'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1411.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:16:27'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1412.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:16:30'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1413.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:16:34'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1414.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:16:50'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1415.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:18:16'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1416.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:19:04'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1417.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:19:08'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1418.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:19:11'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1419.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:19:22'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1420.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:20:31'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1421.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:21:14'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1422.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:21:18'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1423.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:21:23'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1424.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:27:12'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1425.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:29:26'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1426.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:29:30'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1427.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:29:38'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1428.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:29:41'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1429.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:31:43'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1430.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:31:50'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1431.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:32:17'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1432.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:34:17'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1433.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:35:55'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1434.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:37:17'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1435.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:38:46'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1436.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:40:22'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1437.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:40:28'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1438.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:59:07'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1439.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:59:21'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1440.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 16:59:31'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1441.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:06'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1442.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:08'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1443.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:11'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1444.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:14'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1445.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:19'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1446.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:26'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1447.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:35'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1448.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:00:40'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1449.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:02:18'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1450.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:02:41'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1451.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:03:46'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1452.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:03:55'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1453.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:03:57'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1454.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:03:59'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1455.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:04:18'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1456.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:45'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1457.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:47'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1458.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:48'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1459.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:50'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1460.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:52'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1461.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:54'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1462.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:58'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1463.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:08:59'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1464.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:09:02'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1465.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:09:04'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1466.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:10:02'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1467.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:10:10'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1468.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:11:32'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1469.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:11:34'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1470.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:13:16'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1471.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:14:32'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1473.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:14:40'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1474.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:14:46'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1475.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:14:48'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1476.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:15:01'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1477.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:16:01'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1478.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:16:04'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1479.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:16:06'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1480.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 17:16:07'
  WHERE original_filename = '2026-03-28_100EOS5D_AAAA1481.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:01'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1489.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:27'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1490.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:30'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1491.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:32'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1492.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:35'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1493.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:39'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1494.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:43'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1495.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:48'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1496.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:51'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1497.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:55'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1498.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:29:58'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1499.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:00'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1500.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:03'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1501.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:06'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1502.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:09'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1503.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:12'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1504.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:44'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1505.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:47'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1506.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:49'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1507.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:51'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1508.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:54'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1509.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:30:55'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1510.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:31:01'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1511.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:31:16'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1512.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:31:26'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1513.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:33:14'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1514.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:33:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1515.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:24'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1516.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:28'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1517.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:46'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1518.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:51'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1519.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:52'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1520.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:54'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1521.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:34:57'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1522.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:36:53'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1523.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:38:09'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1524.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:38:10'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1525.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:38:12'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1526.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:40:10'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1527.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:40:14'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1528.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:41:35'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1529.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:41:54'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1530.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:42:00'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1531.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:42:31'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1532.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:42:48'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1533.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:44:15'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1534.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:44:20'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1535.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:44:21'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1536.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:44:23'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1537.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:14'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1538.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:15'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1539.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:17'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1540.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:19'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1541.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:21'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1542.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1543.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:24'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1544.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:48:25'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1545.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:49:56'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1546.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:49:59'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1547.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:50:02'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1548.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:50:05'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1549.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:50:07'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1550.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:50:10'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1551.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:50:11'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1552.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:16'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1554.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:20'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1555.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1556.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:24'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1557.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:27'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1558.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:29'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1559.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:33'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1560.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:35'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1561.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:37'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1562.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:40'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1563.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:42'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1564.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:47'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1565.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:50'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1566.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:52'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1567.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:55'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1568.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:57'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1569.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:51:59'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1570.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:52:02'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1571.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:52:08'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1572.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:52:10'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1573.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:21'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1574.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:23'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1575.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:25'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1576.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:26'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1577.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:28'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1578.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:30'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1579.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:31'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1580.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:33'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1581.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:34'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1582.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:36'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1583.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:37'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1584.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:38'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1585.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:40'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1586.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:44'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1587.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:45'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1588.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:47'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1589.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:49'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1590.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:50'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1591.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:52'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1592.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:55:53'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1593.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:57:13'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1594.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:58:33'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1595.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:58:37'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1596.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:58:39'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1597.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:58:50'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1598.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:58:55'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1599.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:01'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1600.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:08'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1601.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:39'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1602.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:47'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1603.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:49'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1604.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:52'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1605.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 16:59:56'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1606.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:00'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1607.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:02'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1608.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:05'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1609.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:08'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1610.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:11'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1611.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:14'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1612.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:23'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1613.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:54'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1614.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:56'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1615.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:00:59'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1616.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:02'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1617.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:08'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1618.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:11'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1619.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:13'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1620.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:15'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1621.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:17'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1622.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:20'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1623.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1624.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:24'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1625.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:27'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1626.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:01:29'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1627.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:43'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1628.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:45'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1629.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:51'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1630.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:53'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1631.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:55'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1632.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:57'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1633.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:06:59'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1634.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:01'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1635.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:03'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1636.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:05'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1637.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:08'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1638.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:10'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1639.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:12'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1640.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:14'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1641.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:16'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1642.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:18'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1643.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:20'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1644.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1645.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:24'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1646.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:27'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1647.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:29'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1648.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:31'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1649.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:34'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1650.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:37'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1651.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:41'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1652.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:07:42'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1653.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:11:09'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1654.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:11:12'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1655.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:15:19'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1656.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:16:38'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1659.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:18:30'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1661.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:19:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1662.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:19:47'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1663.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:21:54'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1664.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:22:31'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1667.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:22:33'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1668.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:22:34'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1669.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:22:36'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1670.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:22:38'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1671.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:22:42'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1672.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:23:00'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1673.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:23:26'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1674.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:24:58'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1675.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:25:00'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1676.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:25:05'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1677.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:25:07'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1678.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:25:11'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1679.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-30 17:25:22'
  WHERE original_filename = '2026-03-30_100EOS5D_AAAA1680.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-04-23 17:24:03'
  WHERE original_filename = '2026-04-23_100EOS5D_AAAA3089---2026-04-23_100EOS5D_AAAA3139.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-04-27 13:17:57'
  WHERE original_filename = '2026-04-27_100EOS5D_AAAA3725---2026-04-27_100EOS5D_AAAA3787.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-05 15:03:54'
  WHERE original_filename = '2026-05-05_100EOS5D_AAAA4676---2026-05-05_100EOS5D_AAAA4682.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-05 16:24:14'
  WHERE original_filename = '2026-05-05_100EOS5D_AAAA4826---2026-05-05_100EOS5D_AAAA4886.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-05 17:17:00'
  WHERE original_filename = '2026-05-05_100EOS5D_AAAA5081---2026-05-05_100EOS5D_AAAA5087.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-05 17:34:16'
  WHERE original_filename = '2026-05-05_100EOS5D_AAAA5106---2026-05-05_100EOS5D_AAAA5114.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-10 15:36:29'
  WHERE original_filename = '2026-05-10_100EOS5D_AAAB5995---2026-05-10_100EOS5D_AAAB6015.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-10 15:44:16'
  WHERE original_filename = '2026-05-10_100EOS5D_AAAB6019---2026-05-10_100EOS5D_AAAB6037.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-10 15:48:16'
  WHERE original_filename = '2026-05-10_100EOS5D_AAAB6038---2026-05-10_100EOS5D_AAAB6042.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-25 14:51:11'
  WHERE original_filename = '2026-05-25_100EOS5D_AAAB6724---2026-05-25_100EOS5D_AAAB6730.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-29 15:47:34'
  WHERE original_filename = '2026-05-29_100EOS5D_AAAB6922---2026-05-29_100EOS5D_AAAB6943.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-05-30 11:33:38'
  WHERE original_filename = '2026-05-30_100EOS5D_AAAB7011---2026-05-30_100EOS5D_AAAB7019.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-06-08 09:15:23'
  WHERE original_filename = '2026-06-08_100EOS5D_AAAB7037---2026-06-08_100EOS5D_AAAB7060.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-06-08 09:21:28'
  WHERE original_filename = '2026-06-08_100EOS5D_AAAB7063---2026-06-08_100EOS5D_AAAB7065.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-06-08 09:55:09'
  WHERE original_filename = '2026-06-08_100EOS5D_AAAB7082---2026-06-08_100EOS5D_AAAB7096.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-06-08 11:21:33'
  WHERE original_filename = '2026-06-08_100EOS5D_AAAB7100---2026-06-08_100EOS5D_AAAB7102.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-06-08 11:29:33'
  WHERE original_filename = '2026-06-08_100EOS5D_AAAB7105---2026-06-08_100EOS5D_AAAB7107.exr' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:53:18'
  WHERE original_filename = 'BBBB0001.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:53:22'
  WHERE original_filename = 'BBBB0002.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:53:26'
  WHERE original_filename = 'BBBB0003.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:54:22'
  WHERE original_filename = 'BBBB0004.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:54:33'
  WHERE original_filename = 'BBBB0005.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 08:57:16'
  WHERE original_filename = 'BBBB0006.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:01:27'
  WHERE original_filename = 'BBBB0007.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:03:00'
  WHERE original_filename = 'BBBB0010.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:03:00'
  WHERE original_filename = 'BBBB0011.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:03:34'
  WHERE original_filename = 'BBBB0012.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:03:43'
  WHERE original_filename = 'BBBB0013.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:03:56'
  WHERE original_filename = 'BBBB0014.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:04:11'
  WHERE original_filename = 'BBBB0015.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:07'
  WHERE original_filename = 'BBBB0016.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:11'
  WHERE original_filename = 'BBBB0017.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:13'
  WHERE original_filename = 'BBBB0018.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:16'
  WHERE original_filename = 'BBBB0019.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:18'
  WHERE original_filename = 'BBBB0020.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:21'
  WHERE original_filename = 'BBBB0021.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:25'
  WHERE original_filename = 'BBBB0022.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:27'
  WHERE original_filename = 'BBBB0023.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:29'
  WHERE original_filename = 'BBBB0024.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:33'
  WHERE original_filename = 'BBBB0025.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:35'
  WHERE original_filename = 'BBBB0026.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:38'
  WHERE original_filename = 'BBBB0027.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:39'
  WHERE original_filename = 'BBBB0028.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:49'
  WHERE original_filename = 'BBBB0029.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:52'
  WHERE original_filename = 'BBBB0030.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:08:58'
  WHERE original_filename = 'BBBB0031.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:00'
  WHERE original_filename = 'BBBB0032.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:02'
  WHERE original_filename = 'BBBB0033.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:05'
  WHERE original_filename = 'BBBB0034.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:07'
  WHERE original_filename = 'BBBB0035.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:10'
  WHERE original_filename = 'BBBB0036.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:12'
  WHERE original_filename = 'BBBB0037.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:14'
  WHERE original_filename = 'BBBB0038.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:17'
  WHERE original_filename = 'BBBB0039.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:19'
  WHERE original_filename = 'BBBB0040.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:21'
  WHERE original_filename = 'BBBB0041.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:09:23'
  WHERE original_filename = 'BBBB0042.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:19'
  WHERE original_filename = 'BBBB0043.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:21'
  WHERE original_filename = 'BBBB0044.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:24'
  WHERE original_filename = 'BBBB0045.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:26'
  WHERE original_filename = 'BBBB0046.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:28'
  WHERE original_filename = 'BBBB0047.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:31'
  WHERE original_filename = 'BBBB0048.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:33'
  WHERE original_filename = 'BBBB0049.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:36'
  WHERE original_filename = 'BBBB0050.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:38'
  WHERE original_filename = 'BBBB0051.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:42'
  WHERE original_filename = 'BBBB0052.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:45'
  WHERE original_filename = 'BBBB0053.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:50'
  WHERE original_filename = 'BBBB0054.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:51'
  WHERE original_filename = 'BBBB0055.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:53'
  WHERE original_filename = 'BBBB0056.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:56'
  WHERE original_filename = 'BBBB0057.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:11:58'
  WHERE original_filename = 'BBBB0058.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:00'
  WHERE original_filename = 'BBBB0059.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:03'
  WHERE original_filename = 'BBBB0060.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:05'
  WHERE original_filename = 'BBBB0061.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:17'
  WHERE original_filename = 'BBBB0062.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:18'
  WHERE original_filename = 'BBBB0063.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:33'
  WHERE original_filename = 'BBBB0064.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:35'
  WHERE original_filename = 'BBBB0065.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:37'
  WHERE original_filename = 'BBBB0066.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:39'
  WHERE original_filename = 'BBBB0067.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:41'
  WHERE original_filename = 'BBBB0068.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:42'
  WHERE original_filename = 'BBBB0069.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:44'
  WHERE original_filename = 'BBBB0070.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:47'
  WHERE original_filename = 'BBBB0071.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:48'
  WHERE original_filename = 'BBBB0072.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:50'
  WHERE original_filename = 'BBBB0073.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:52'
  WHERE original_filename = 'BBBB0074.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:53'
  WHERE original_filename = 'BBBB0075.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:12:59'
  WHERE original_filename = 'BBBB0076.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:00'
  WHERE original_filename = 'BBBB0077.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:08'
  WHERE original_filename = 'BBBB0078.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:09'
  WHERE original_filename = 'BBBB0079.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:11'
  WHERE original_filename = 'BBBB0080.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:13'
  WHERE original_filename = 'BBBB0081.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:16'
  WHERE original_filename = 'BBBB0082.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:18'
  WHERE original_filename = 'BBBB0083.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:24'
  WHERE original_filename = 'BBBB0084.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:27'
  WHERE original_filename = 'BBBB0085.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:34'
  WHERE original_filename = 'BBBB0086.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:36'
  WHERE original_filename = 'BBBB0087.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:44'
  WHERE original_filename = 'BBBB0088.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:46'
  WHERE original_filename = 'BBBB0089.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:13:48'
  WHERE original_filename = 'BBBB0090.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:14:45'
  WHERE original_filename = 'BBBB0091.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:14:47'
  WHERE original_filename = 'BBBB0092.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:14:51'
  WHERE original_filename = 'BBBB0093.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:14:53'
  WHERE original_filename = 'BBBB0094.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:14:58'
  WHERE original_filename = 'BBBB0095.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:00'
  WHERE original_filename = 'BBBB0096.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:03'
  WHERE original_filename = 'BBBB0097.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:05'
  WHERE original_filename = 'BBBB0098.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:07'
  WHERE original_filename = 'BBBB0099.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:15'
  WHERE original_filename = 'BBBB0100.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:16'
  WHERE original_filename = 'BBBB0101.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:18'
  WHERE original_filename = 'BBBB0102.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:20'
  WHERE original_filename = 'BBBB0103.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:22'
  WHERE original_filename = 'BBBB0104.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:37'
  WHERE original_filename = 'BBBB0105.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:38'
  WHERE original_filename = 'BBBB0106.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:40'
  WHERE original_filename = 'BBBB0107.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:41'
  WHERE original_filename = 'BBBB0108.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:43'
  WHERE original_filename = 'BBBB0109.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:46'
  WHERE original_filename = 'BBBB0110.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:48'
  WHERE original_filename = 'BBBB0111.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:50'
  WHERE original_filename = 'BBBB0112.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:55'
  WHERE original_filename = 'BBBB0113.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:15:59'
  WHERE original_filename = 'BBBB0114.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:16:02'
  WHERE original_filename = 'BBBB0115.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:16:29'
  WHERE original_filename = 'BBBB0116.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:24:40'
  WHERE original_filename = 'BBBB0117.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:24:42'
  WHERE original_filename = 'BBBB0118.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:24:43'
  WHERE original_filename = 'BBBB0119.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:24:45'
  WHERE original_filename = 'BBBB0120.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:24:49'
  WHERE original_filename = 'BBBB0121.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:24:59'
  WHERE original_filename = 'BBBB0122.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:25:01'
  WHERE original_filename = 'BBBB0123.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:25:03'
  WHERE original_filename = 'BBBB0124.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:25:12'
  WHERE original_filename = 'BBBB0125.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:25:26'
  WHERE original_filename = 'BBBB0126.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:25:28'
  WHERE original_filename = 'BBBB0127.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:27:41'
  WHERE original_filename = 'BBBB0128.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:27:43'
  WHERE original_filename = 'BBBB0129.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:27:45'
  WHERE original_filename = 'BBBB0130.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:04'
  WHERE original_filename = 'BBBB0131.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:05'
  WHERE original_filename = 'BBBB0132.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:07'
  WHERE original_filename = 'BBBB0133.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:08'
  WHERE original_filename = 'BBBB0134.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:10'
  WHERE original_filename = 'BBBB0135.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:12'
  WHERE original_filename = 'BBBB0136.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:14'
  WHERE original_filename = 'BBBB0137.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:16'
  WHERE original_filename = 'BBBB0138.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:19'
  WHERE original_filename = 'BBBB0139.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:21'
  WHERE original_filename = 'BBBB0140.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:22'
  WHERE original_filename = 'BBBB0141.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:24'
  WHERE original_filename = 'BBBB0142.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:26'
  WHERE original_filename = 'BBBB0143.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:30'
  WHERE original_filename = 'BBBB0144.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:32'
  WHERE original_filename = 'BBBB0145.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:35'
  WHERE original_filename = 'BBBB0146.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:36'
  WHERE original_filename = 'BBBB0147.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:39'
  WHERE original_filename = 'BBBB0148.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:42'
  WHERE original_filename = 'BBBB0149.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:44'
  WHERE original_filename = 'BBBB0150.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:46'
  WHERE original_filename = 'BBBB0151.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:48'
  WHERE original_filename = 'BBBB0152.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:49'
  WHERE original_filename = 'BBBB0153.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:37:51'
  WHERE original_filename = 'BBBB0154.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:00'
  WHERE original_filename = 'BBBB0157.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:01'
  WHERE original_filename = 'BBBB0158.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:03'
  WHERE original_filename = 'BBBB0159.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:05'
  WHERE original_filename = 'BBBB0160.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:06'
  WHERE original_filename = 'BBBB0161.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:08'
  WHERE original_filename = 'BBBB0162.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:10'
  WHERE original_filename = 'BBBB0163.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:11'
  WHERE original_filename = 'BBBB0164.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:13'
  WHERE original_filename = 'BBBB0165.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:15'
  WHERE original_filename = 'BBBB0166.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:17'
  WHERE original_filename = 'BBBB0167.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:18'
  WHERE original_filename = 'BBBB0168.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:42:21'
  WHERE original_filename = 'BBBB0169.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:03'
  WHERE original_filename = 'BBBB0170.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:06'
  WHERE original_filename = 'BBBB0171.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:10'
  WHERE original_filename = 'BBBB0172.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:13'
  WHERE original_filename = 'BBBB0173.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:17'
  WHERE original_filename = 'BBBB0174.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:21'
  WHERE original_filename = 'BBBB0175.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:24'
  WHERE original_filename = 'BBBB0176.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:26'
  WHERE original_filename = 'BBBB0177.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:29'
  WHERE original_filename = 'BBBB0178.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:37'
  WHERE original_filename = 'BBBB0179.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:39'
  WHERE original_filename = 'BBBB0180.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:41'
  WHERE original_filename = 'BBBB0181.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:46'
  WHERE original_filename = 'BBBB0182.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:50'
  WHERE original_filename = 'BBBB0183.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:52'
  WHERE original_filename = 'BBBB0184.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:55'
  WHERE original_filename = 'BBBB0185.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:49:58'
  WHERE original_filename = 'BBBB0186.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:00'
  WHERE original_filename = 'BBBB0187.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:07'
  WHERE original_filename = 'BBBB0188.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:09'
  WHERE original_filename = 'BBBB0189.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:11'
  WHERE original_filename = 'BBBB0190.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:14'
  WHERE original_filename = 'BBBB0191.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:16'
  WHERE original_filename = 'BBBB0192.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:18'
  WHERE original_filename = 'BBBB0193.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:22'
  WHERE original_filename = 'BBBB0194.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:25'
  WHERE original_filename = 'BBBB0195.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:27'
  WHERE original_filename = 'BBBB0196.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:39'
  WHERE original_filename = 'BBBB0197.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:41'
  WHERE original_filename = 'BBBB0198.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:45'
  WHERE original_filename = 'BBBB0199.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:47'
  WHERE original_filename = 'BBBB0200.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:51'
  WHERE original_filename = 'BBBB0201.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:50:59'
  WHERE original_filename = 'BBBB0202.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:51:00'
  WHERE original_filename = 'BBBB0203.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:51:03'
  WHERE original_filename = 'BBBB0204.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:51:10'
  WHERE original_filename = 'BBBB0205.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:51:12'
  WHERE original_filename = 'BBBB0206.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:51:15'
  WHERE original_filename = 'BBBB0207.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:51:18'
  WHERE original_filename = 'BBBB0208.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:54:40'
  WHERE original_filename = 'BBBB0209.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:54:42'
  WHERE original_filename = 'BBBB0210.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:54:56'
  WHERE original_filename = 'BBBB0211.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:55:05'
  WHERE original_filename = 'BBBB0212.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:57:26'
  WHERE original_filename = 'BBBB0213.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:57:34'
  WHERE original_filename = 'BBBB0214.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:57:45'
  WHERE original_filename = 'BBBB0215.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:58:39'
  WHERE original_filename = 'BBBB0216.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:58:42'
  WHERE original_filename = 'BBBB0217.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:58:53'
  WHERE original_filename = 'BBBB0218.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:59:02'
  WHERE original_filename = 'BBBB0219.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:59:07'
  WHERE original_filename = 'BBBB0220.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:59:08'
  WHERE original_filename = 'BBBB0221.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 09:59:09'
  WHERE original_filename = 'BBBB0222.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:00:09'
  WHERE original_filename = 'BBBB0223.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:00:43'
  WHERE original_filename = 'BBBB0224.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:03:32'
  WHERE original_filename = 'BBBB0225.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:03:41'
  WHERE original_filename = 'BBBB0226.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:04:29'
  WHERE original_filename = 'BBBB0227.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:04:30'
  WHERE original_filename = 'BBBB0228.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:04:33'
  WHERE original_filename = 'BBBB0229.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:04:35'
  WHERE original_filename = 'BBBB0230.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:04:37'
  WHERE original_filename = 'BBBB0231.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:03'
  WHERE original_filename = 'BBBB0232.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:04'
  WHERE original_filename = 'BBBB0233.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:06'
  WHERE original_filename = 'BBBB0234.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:07'
  WHERE original_filename = 'BBBB0235.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:09'
  WHERE original_filename = 'BBBB0236.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:10'
  WHERE original_filename = 'BBBB0237.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:12'
  WHERE original_filename = 'BBBB0238.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:13'
  WHERE original_filename = 'BBBB0239.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:14'
  WHERE original_filename = 'BBBB0240.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:22'
  WHERE original_filename = 'BBBB0241.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:23'
  WHERE original_filename = 'BBBB0242.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:24'
  WHERE original_filename = 'BBBB0243.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:25'
  WHERE original_filename = 'BBBB0244.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:28'
  WHERE original_filename = 'BBBB0245.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:30'
  WHERE original_filename = 'BBBB0246.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:31'
  WHERE original_filename = 'BBBB0247.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:05:32'
  WHERE original_filename = 'BBBB0248.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:10:05'
  WHERE original_filename = 'BBBB0249.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:10:08'
  WHERE original_filename = 'BBBB0250.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:12:06'
  WHERE original_filename = 'BBBB0251.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:12:07'
  WHERE original_filename = 'BBBB0252.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:12:29'
  WHERE original_filename = 'BBBB0253.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:12:30'
  WHERE original_filename = 'BBBB0254.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:12:58'
  WHERE original_filename = 'BBBB0255.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:13:15'
  WHERE original_filename = 'BBBB0256.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:13:30'
  WHERE original_filename = 'BBBB0257.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:13:51'
  WHERE original_filename = 'BBBB0258.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:13:53'
  WHERE original_filename = 'BBBB0259.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:18:03'
  WHERE original_filename = 'BBBB0260.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:18:45'
  WHERE original_filename = 'BBBB0261.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:38:01'
  WHERE original_filename = 'BBBB0262.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:38:30'
  WHERE original_filename = 'BBBB0263.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:38:50'
  WHERE original_filename = 'BBBB0264.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:39:14'
  WHERE original_filename = 'BBBB0265.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:40:04'
  WHERE original_filename = 'BBBB0266.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:40:50'
  WHERE original_filename = 'BBBB0267.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:40:54'
  WHERE original_filename = 'BBBB0268.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:41:00'
  WHERE original_filename = 'BBBB0269.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:41:09'
  WHERE original_filename = 'BBBB0270.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:41:46'
  WHERE original_filename = 'BBBB0271.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:06'
  WHERE original_filename = 'BBBB0272.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:30'
  WHERE original_filename = 'BBBB0273.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:32'
  WHERE original_filename = 'BBBB0274.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:35'
  WHERE original_filename = 'BBBB0275.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:38'
  WHERE original_filename = 'BBBB0276.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:41'
  WHERE original_filename = 'BBBB0277.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:42:43'
  WHERE original_filename = 'BBBB0278.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:43:27'
  WHERE original_filename = 'BBBB0279.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:44:03'
  WHERE original_filename = 'BBBB0280.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:44:30'
  WHERE original_filename = 'BBBB0281.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:44:56'
  WHERE original_filename = 'BBBB0282.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:45:21'
  WHERE original_filename = 'BBBB0283.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:45:32'
  WHERE original_filename = 'BBBB0284.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:45:44'
  WHERE original_filename = 'BBBB0285.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:45:59'
  WHERE original_filename = 'BBBB0286.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:46:15'
  WHERE original_filename = 'BBBB0287.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:46:34'
  WHERE original_filename = 'BBBB0288.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:50:01'
  WHERE original_filename = 'BBBB0289.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:50:10'
  WHERE original_filename = 'BBBB0290.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:50:35'
  WHERE original_filename = 'BBBB0291.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:52:12'
  WHERE original_filename = 'BBBB0292.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 10:52:24'
  WHERE original_filename = 'BBBB0293.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:30'
  WHERE original_filename = 'BBBB0294.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:32'
  WHERE original_filename = 'BBBB0295.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:35'
  WHERE original_filename = 'BBBB0296.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:42'
  WHERE original_filename = 'BBBB0297.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:46'
  WHERE original_filename = 'BBBB0298.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:49'
  WHERE original_filename = 'BBBB0299.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:51'
  WHERE original_filename = 'BBBB0300.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:54'
  WHERE original_filename = 'BBBB0301.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:01:56'
  WHERE original_filename = 'BBBB0302.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:02:02'
  WHERE original_filename = 'BBBB0303.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:02:06'
  WHERE original_filename = 'BBBB0304.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:33:03'
  WHERE original_filename = 'BBBB0305.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:33:47'
  WHERE original_filename = 'BBBB0306.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:36:34'
  WHERE original_filename = 'BBBB0307.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 11:38:04'
  WHERE original_filename = 'BBBB0311.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:26:15'
  WHERE original_filename = 'BBBB0312.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:26:17'
  WHERE original_filename = 'BBBB0313.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:26:21'
  WHERE original_filename = 'BBBB0314.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:26:24'
  WHERE original_filename = 'BBBB0315.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:27:43'
  WHERE original_filename = 'BBBB0316.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:29:03'
  WHERE original_filename = 'BBBB0317.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:30:28'
  WHERE original_filename = 'BBBB0318.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:30:34'
  WHERE original_filename = 'BBBB0319.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:31:21'
  WHERE original_filename = 'BBBB0320.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:31:41'
  WHERE original_filename = 'BBBB0321.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:35:56'
  WHERE original_filename = 'BBBB0322.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:36:02'
  WHERE original_filename = 'BBBB0323.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:36:19'
  WHERE original_filename = 'BBBB0324.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:36:37'
  WHERE original_filename = 'BBBB0325.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:39:44'
  WHERE original_filename = 'BBBB0326.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:42:19'
  WHERE original_filename = 'BBBB0327.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:42:32'
  WHERE original_filename = 'BBBB0328.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:42:42'
  WHERE original_filename = 'BBBB0329.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:42:47'
  WHERE original_filename = 'BBBB0330.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:43:50'
  WHERE original_filename = 'BBBB0331.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:44:05'
  WHERE original_filename = 'BBBB0332.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:44:21'
  WHERE original_filename = 'BBBB0333.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:44:31'
  WHERE original_filename = 'BBBB0334.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:44:49'
  WHERE original_filename = 'BBBB0335.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:45:08'
  WHERE original_filename = 'BBBB0336.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:45:15'
  WHERE original_filename = 'BBBB0337.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:47:22'
  WHERE original_filename = 'BBBB0338.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:51:01'
  WHERE original_filename = 'BBBB0339.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:32'
  WHERE original_filename = 'BBBB0340.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:33'
  WHERE original_filename = 'BBBB0341.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:34'
  WHERE original_filename = 'BBBB0342.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:36'
  WHERE original_filename = 'BBBB0343.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:37'
  WHERE original_filename = 'BBBB0344.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:39'
  WHERE original_filename = 'BBBB0345.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:40'
  WHERE original_filename = 'BBBB0346.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:41'
  WHERE original_filename = 'BBBB0347.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:43'
  WHERE original_filename = 'BBBB0348.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 12:53:45'
  WHERE original_filename = 'BBBB0349.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:01:44'
  WHERE original_filename = 'BBBB0350.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:01:47'
  WHERE original_filename = 'BBBB0351.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:01:56'
  WHERE original_filename = 'BBBB0352.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:02:39'
  WHERE original_filename = 'BBBB0353.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:02:55'
  WHERE original_filename = 'BBBB0354.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:02:58'
  WHERE original_filename = 'BBBB0355.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:03:49'
  WHERE original_filename = 'BBBB0356.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:03:50'
  WHERE original_filename = 'BBBB0357.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:03:52'
  WHERE original_filename = 'BBBB0358.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:03:54'
  WHERE original_filename = 'BBBB0359.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:03:55'
  WHERE original_filename = 'BBBB0360.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:03:57'
  WHERE original_filename = 'BBBB0361.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:04:29'
  WHERE original_filename = 'BBBB0362.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:04:51'
  WHERE original_filename = 'BBBB0363.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:05:01'
  WHERE original_filename = 'BBBB0364.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:05:49'
  WHERE original_filename = 'BBBB0365.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:05:58'
  WHERE original_filename = 'BBBB0366.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:05:59'
  WHERE original_filename = 'BBBB0367.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:01'
  WHERE original_filename = 'BBBB0368.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:03'
  WHERE original_filename = 'BBBB0369.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:05'
  WHERE original_filename = 'BBBB0370.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:07'
  WHERE original_filename = 'BBBB0371.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:09'
  WHERE original_filename = 'BBBB0372.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:10'
  WHERE original_filename = 'BBBB0373.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:28'
  WHERE original_filename = 'BBBB0374.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:29'
  WHERE original_filename = 'BBBB0375.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:31'
  WHERE original_filename = 'BBBB0376.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:32'
  WHERE original_filename = 'BBBB0377.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:06:34'
  WHERE original_filename = 'BBBB0378.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:09:33'
  WHERE original_filename = 'BBBB0379.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:09:34'
  WHERE original_filename = 'BBBB0380.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:09:36'
  WHERE original_filename = 'BBBB0381.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:11:31'
  WHERE original_filename = 'BBBB0382.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:11:40'
  WHERE original_filename = 'BBBB0383.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:11:48'
  WHERE original_filename = 'BBBB0384.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:00'
  WHERE original_filename = 'BBBB0385.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:05'
  WHERE original_filename = 'BBBB0386.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:21'
  WHERE original_filename = 'BBBB0387.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:32'
  WHERE original_filename = 'BBBB0388.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:34'
  WHERE original_filename = 'BBBB0389.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:35'
  WHERE original_filename = 'BBBB0390.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:38'
  WHERE original_filename = 'BBBB0391.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:43'
  WHERE original_filename = 'BBBB0392.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:44'
  WHERE original_filename = 'BBBB0393.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:46'
  WHERE original_filename = 'BBBB0394.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:48'
  WHERE original_filename = 'BBBB0395.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:49'
  WHERE original_filename = 'BBBB0396.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:51'
  WHERE original_filename = 'BBBB0397.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:53'
  WHERE original_filename = 'BBBB0398.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:54'
  WHERE original_filename = 'BBBB0399.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:12:59'
  WHERE original_filename = 'BBBB0400.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:13:01'
  WHERE original_filename = 'BBBB0401.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:13:03'
  WHERE original_filename = 'BBBB0402.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:15:24'
  WHERE original_filename = 'BBBB0403.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:15:58'
  WHERE original_filename = 'BBBB0404.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:16:17'
  WHERE original_filename = 'BBBB0405.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:00'
  WHERE original_filename = 'BBBB0406.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:25'
  WHERE original_filename = 'BBBB0407.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:31'
  WHERE original_filename = 'BBBB0408.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:34'
  WHERE original_filename = 'BBBB0409.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:43'
  WHERE original_filename = 'BBBB0410.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:50'
  WHERE original_filename = 'BBBB0411.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:19:54'
  WHERE original_filename = 'BBBB0412.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:11'
  WHERE original_filename = 'BBBB0413.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:15'
  WHERE original_filename = 'BBBB0414.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:31'
  WHERE original_filename = 'BBBB0415.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:35'
  WHERE original_filename = 'BBBB0416.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:39'
  WHERE original_filename = 'BBBB0417.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:44'
  WHERE original_filename = 'BBBB0418.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:48'
  WHERE original_filename = 'BBBB0419.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:55'
  WHERE original_filename = 'BBBB0420.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:20:58'
  WHERE original_filename = 'BBBB0421.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:21:03'
  WHERE original_filename = 'BBBB0422.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:21:07'
  WHERE original_filename = 'BBBB0423.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:21:11'
  WHERE original_filename = 'BBBB0424.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:44'
  WHERE original_filename = 'BBBB0432.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:46'
  WHERE original_filename = 'BBBB0433.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:48'
  WHERE original_filename = 'BBBB0434.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:49'
  WHERE original_filename = 'BBBB0435.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:50'
  WHERE original_filename = 'BBBB0436.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:52'
  WHERE original_filename = 'BBBB0437.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:53'
  WHERE original_filename = 'BBBB0438.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:41:55'
  WHERE original_filename = 'BBBB0439.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:42:33'
  WHERE original_filename = 'BBBB0440.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:18'
  WHERE original_filename = 'BBBB0441.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:19'
  WHERE original_filename = 'BBBB0442.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:21'
  WHERE original_filename = 'BBBB0443.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:23'
  WHERE original_filename = 'BBBB0444.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:24'
  WHERE original_filename = 'BBBB0445.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:26'
  WHERE original_filename = 'BBBB0446.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:27'
  WHERE original_filename = 'BBBB0447.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:47:34'
  WHERE original_filename = 'BBBB0448.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:51:15'
  WHERE original_filename = 'BBBB0449.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:51:28'
  WHERE original_filename = 'BBBB0450.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:55:53'
  WHERE original_filename = 'BBBB0451.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:56:06'
  WHERE original_filename = 'BBBB0452.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:59:23'
  WHERE original_filename = 'BBBB0453.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:59:26'
  WHERE original_filename = 'BBBB0454.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-23 13:59:30'
  WHERE original_filename = 'BBBB0455.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-01-01 14:05:43'
  WHERE original_filename = '_36A7727 - _36A7738.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:10:03'
  WHERE original_filename = '_36A8016.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:10:39'
  WHERE original_filename = '_36A8017.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:10:46'
  WHERE original_filename = '_36A8018.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:10:54'
  WHERE original_filename = '_36A8019.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:02'
  WHERE original_filename = '_36A8020.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:13'
  WHERE original_filename = '_36A8021.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:24'
  WHERE original_filename = '_36A8022.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:32'
  WHERE original_filename = '_36A8023.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:39'
  WHERE original_filename = '_36A8024.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:47'
  WHERE original_filename = '_36A8025.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:54'
  WHERE original_filename = '_36A8026.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:11:59'
  WHERE original_filename = '_36A8027.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:12:05'
  WHERE original_filename = '_36A8028.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:12:11'
  WHERE original_filename = '_36A8029.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:12:16'
  WHERE original_filename = '_36A8030.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:12:22'
  WHERE original_filename = '_36A8031.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:12:29'
  WHERE original_filename = '_36A8032.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:12:52'
  WHERE original_filename = '_36A8035.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:03'
  WHERE original_filename = '_36A8037.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:09'
  WHERE original_filename = '_36A8038.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:16'
  WHERE original_filename = '_36A8039.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:22'
  WHERE original_filename = '_36A8040.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:27'
  WHERE original_filename = '_36A8041.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:36'
  WHERE original_filename = '_36A8042.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:43'
  WHERE original_filename = '_36A8043.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:49'
  WHERE original_filename = '_36A8044.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:13:56'
  WHERE original_filename = '_36A8045.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:01'
  WHERE original_filename = '_36A8046.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:08'
  WHERE original_filename = '_36A8047.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:14'
  WHERE original_filename = '_36A8048.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:20'
  WHERE original_filename = '_36A8049.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:27'
  WHERE original_filename = '_36A8050.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:34'
  WHERE original_filename = '_36A8051.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:40'
  WHERE original_filename = '_36A8052.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-10 14:14:48'
  WHERE original_filename = '_36A8053.JPG' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:09:41'
  WHERE original_filename = '_36A8327.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-02-12 08:45:02'
  WHERE original_filename = '_36A8406.tiff' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:29'
  WHERE original_filename = '_36A8852.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:30'
  WHERE original_filename = '_36A8853.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:32'
  WHERE original_filename = '_36A8854.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:33'
  WHERE original_filename = '_36A8855.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:34'
  WHERE original_filename = '_36A8856.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:36'
  WHERE original_filename = '_36A8857.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:37'
  WHERE original_filename = '_36A8858.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:39'
  WHERE original_filename = '_36A8859.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:44'
  WHERE original_filename = '_36A8860.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:46'
  WHERE original_filename = '_36A8861.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:47'
  WHERE original_filename = '_36A8862.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:51'
  WHERE original_filename = '_36A8863.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:54'
  WHERE original_filename = '_36A8864.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:15:56'
  WHERE original_filename = '_36A8865.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:02'
  WHERE original_filename = '_36A8866.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:04'
  WHERE original_filename = '_36A8867.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:05'
  WHERE original_filename = '_36A8868.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:07'
  WHERE original_filename = '_36A8869.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:09'
  WHERE original_filename = '_36A8870.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:10'
  WHERE original_filename = '_36A8871.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:14'
  WHERE original_filename = '_36A8872.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:15'
  WHERE original_filename = '_36A8873.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:16'
  WHERE original_filename = '_36A8874.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:18'
  WHERE original_filename = '_36A8875.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:19'
  WHERE original_filename = '_36A8876.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:20'
  WHERE original_filename = '_36A8877.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:21'
  WHERE original_filename = '_36A8878.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:23'
  WHERE original_filename = '_36A8879.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:37'
  WHERE original_filename = '_36A8880.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:38'
  WHERE original_filename = '_36A8881.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:40'
  WHERE original_filename = '_36A8882.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:42'
  WHERE original_filename = '_36A8883.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:44'
  WHERE original_filename = '_36A8884.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:46'
  WHERE original_filename = '_36A8885.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:47'
  WHERE original_filename = '_36A8886.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:49'
  WHERE original_filename = '_36A8887.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:51'
  WHERE original_filename = '_36A8888.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:57'
  WHERE original_filename = '_36A8889.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:16:59'
  WHERE original_filename = '_36A8890.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:01'
  WHERE original_filename = '_36A8891.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:02'
  WHERE original_filename = '_36A8892.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:03'
  WHERE original_filename = '_36A8893.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:04'
  WHERE original_filename = '_36A8894.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:06'
  WHERE original_filename = '_36A8895.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:07'
  WHERE original_filename = '_36A8896.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:08'
  WHERE original_filename = '_36A8897.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:11'
  WHERE original_filename = '_36A8898.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:22'
  WHERE original_filename = '_36A8899.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:24'
  WHERE original_filename = '_36A8900.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:26'
  WHERE original_filename = '_36A8901.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:35'
  WHERE original_filename = '_36A8902.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:41'
  WHERE original_filename = '_36A8903.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:42'
  WHERE original_filename = '_36A8904.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:44'
  WHERE original_filename = '_36A8905.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:46'
  WHERE original_filename = '_36A8906.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:48'
  WHERE original_filename = '_36A8907.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:57'
  WHERE original_filename = '_36A8908.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:17:59'
  WHERE original_filename = '_36A8909.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:18:01'
  WHERE original_filename = '_36A8910.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:18:05'
  WHERE original_filename = '_36A8911.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:18:14'
  WHERE original_filename = '_36A8912.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-10 16:34:34'
  WHERE original_filename = '_36A8951.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:24:56'
  WHERE original_filename = '_36A9012.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:26:06'
  WHERE original_filename = '_36A9014.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:27:35'
  WHERE original_filename = '_36A9016.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:27:58'
  WHERE original_filename = '_36A9017.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:38:18'
  WHERE original_filename = '_36A9037.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:38:21'
  WHERE original_filename = '_36A9038.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:38:24'
  WHERE original_filename = '_36A9039.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:38:27'
  WHERE original_filename = '_36A9040.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:38:31'
  WHERE original_filename = '_36A9041.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:41:46'
  WHERE original_filename = '_36A9042.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:42:13'
  WHERE original_filename = '_36A9043.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:42:15'
  WHERE original_filename = '_36A9044.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:42:18'
  WHERE original_filename = '_36A9045.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:42:22'
  WHERE original_filename = '_36A9046.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:42:25'
  WHERE original_filename = '_36A9047.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-12 17:42:31'
  WHERE original_filename = '_36A9048.webp' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 09:52:25'
  WHERE original_filename = 'p_036A0457-036A0467-11.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:47:43'
  WHERE original_filename = 'p_036A0479---036A0486-8.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:50:36'
  WHERE original_filename = 'p_036A0487-036A0496-10-e.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-27 10:53:46'
  WHERE original_filename = 'p_036A0508---036A0523-16.tif' AND deleted = false;
UPDATE photos SET captured_at = '2026-03-28 14:17:32'
  WHERE original_filename = 'p_2026-03-28_100EOS5D_AAAA1025-2026-03-28_100EOS5D_AAAA1035-11-e-conv.tif' AND deleted = false;
COMMIT;
