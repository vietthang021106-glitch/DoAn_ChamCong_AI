<?php
declare(strict_types=1);

/** Session-only enrollment state transitions; never writes database rows. */
final class EnrollmentCaptureState
{
    public const STABLE_FRAMES_REQUIRED = 8;

    public static function create(): array
    {
        return [
            'current_pose_index' => 0,
            'stable_frame_count' => 0,
            'last_camera_sequence' => null,
            'samples' => [],
        ];
    }

    public static function poseIndex(array $state): int
    {
        $index = $state['current_pose_index'] ?? count($state['samples'] ?? []);
        if (!is_int($index) || $index !== count($state['samples'] ?? [])) {
            throw new LogicException('Enrollment pose index and sample count are inconsistent.');
        }

        return $index;
    }

    public static function observe(array &$state, bool $ready): array
    {
        if (!$ready) {
            $state['stable_frame_count'] = 0;
        } else {
            $count = max(0, (int)($state['stable_frame_count'] ?? 0));
            $state['stable_frame_count'] = min(self::STABLE_FRAMES_REQUIRED, $count + 1);
        }

        return [
            'ready' => $ready,
            'stable_frame_count' => $state['stable_frame_count'],
            'stable_frames_required' => self::STABLE_FRAMES_REQUIRED,
            'capture_due' => $state['stable_frame_count'] >= self::STABLE_FRAMES_REQUIRED,
        ];
    }

    /** Count only distinct, strictly increasing frames from the shared camera owner. */
    public static function observeSnapshot(array &$state, int $sequence, bool $ready): array
    {
        $lastSequence = $state['last_camera_sequence'] ?? null;
        $fresh = $sequence > 0 && ($lastSequence === null || $sequence > $lastSequence);
        if (!$fresh) {
            $ready = false;
        } else {
            $state['last_camera_sequence'] = $sequence;
        }

        return self::observe($state, $ready) + ['fresh_frame' => $fresh];
    }

    public static function reset(array &$state): void
    {
        $state['stable_frame_count'] = 0;
    }

    public static function recordSample(array &$state, array $poses, string $pose, array $sample): int
    {
        $index = self::poseIndex($state);
        if (!isset($poses[$index]) || $poses[$index] !== $pose) {
            throw new LogicException('Enrollment sample does not match the current pose.');
        }
        if ((int)($state['stable_frame_count'] ?? 0) < self::STABLE_FRAMES_REQUIRED) {
            throw new LogicException('Eight consecutive ready frames are required before capture.');
        }
        if (!isset($sample['vector'], $sample['image'])
            || !is_string($sample['vector']) || !is_string($sample['image'])
            || $sample['vector'] === '' || $sample['image'] === '') {
            throw new LogicException('Enrollment image/vector pair is invalid.');
        }

        $sample['pose'] = $pose;
        $state['samples'][] = $sample;
        $state['current_pose_index'] = $index + 1;
        $state['stable_frame_count'] = 0;

        return $index + 1;
    }
}
