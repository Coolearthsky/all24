package org.team100.lib.localization;

import java.util.List;
import java.util.Map;
import java.util.Map.Entry;

import org.team100.lib.dashboard.Glassy;
import org.team100.lib.logging.SupplierLogger2;
import org.team100.lib.logging.SupplierLogger2.DoubleSupplierLogger2;
import org.team100.lib.logging.SupplierLogger2.Rotation2dLogger;
import org.team100.lib.motion.drivetrain.SwerveState;
import org.team100.lib.motion.drivetrain.kinodynamics.FieldRelativeAcceleration;
import org.team100.lib.motion.drivetrain.kinodynamics.FieldRelativeDelta;
import org.team100.lib.motion.drivetrain.kinodynamics.FieldRelativeVelocity;
import org.team100.lib.motion.drivetrain.kinodynamics.SwerveKinodynamics;
import org.team100.lib.motion.drivetrain.kinodynamics.SwerveModulePosition100;
import org.team100.lib.telemetry.Telemetry.Level;
import org.team100.lib.util.DriveUtil;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Twist2d;

public class SwerveDrivePoseEstimator100 implements PoseEstimator100, Glassy {
    private static final double kBufferDuration = 1.5;
    // look back a little to get a pose for velocity estimation
    private static final double velocityDtS = 0.02;

    private final int m_numModules;
    private final SwerveKinodynamics m_kinodynamics;
    private final TimeInterpolatableBuffer100<InterpolationRecord> m_poseBuffer;
    // LOGGERS
    private final Rotation2dLogger m_log_offset;
    private final DoubleSupplierLogger2 m_log_pose_x;

    /**
     * maintained in resetPosition().
     */
    private Rotation2d m_gyroOffset;

    /**
     * @param kinodynamics      A correctly-configured kinodynamics object
     *                          for your drivetrain.
     * @param gyroAngle         The current gyro angle.
     * @param modulePositions   The current distance and rotation
     *                          measurements of the swerve modules.
     * @param initialPoseMeters The starting pose estimate.
     */
    public SwerveDrivePoseEstimator100(
            SupplierLogger2 parent,
            SwerveKinodynamics kinodynamics,
            Rotation2d gyroAngle,
            SwerveModulePosition100[] modulePositions,
            Pose2d initialPoseMeters,
            double timestampSeconds) {
        SupplierLogger2 child = parent.child(this);
        m_numModules = modulePositions.length;
        m_kinodynamics = kinodynamics;
        m_poseBuffer = new TimeInterpolatableBuffer100<>(
                child,
                kBufferDuration,
                timestampSeconds,
                new InterpolationRecord(
                        m_kinodynamics.getKinematics(),
                        new SwerveState(
                                initialPoseMeters,
                                new FieldRelativeVelocity(0, 0, 0),
                                new FieldRelativeAcceleration(0, 0, 0)),
                        gyroAngle,
                        modulePositions));
        m_gyroOffset = initialPoseMeters.getRotation().minus(gyroAngle);
        m_log_offset = child.rotation2dLogger(Level.TRACE, "GYRO OFFSET");
        m_log_pose_x = child.doubleLogger(Level.TRACE, "posex");
    }

    @Override
    public SwerveState get(double timestampSeconds) {
        return m_poseBuffer.get(timestampSeconds).m_state;
    }

    /** Empty the buffer and add the given measurements. */
    public void reset(
            Rotation2d gyroAngle,
            SwerveModulePosition100[] modulePositions,
            Pose2d pose,
            double timestampSeconds) {

        checkLength(modulePositions);

        m_gyroOffset = pose.getRotation().minus(gyroAngle);

        // empty the buffer and add the current pose
        m_poseBuffer.reset(
                timestampSeconds,
                new InterpolationRecord(
                        m_kinodynamics.getKinematics(),
                        new SwerveState(
                                pose,
                                new FieldRelativeVelocity(0, 0, 0),
                                new FieldRelativeAcceleration(0, 0, 0)),
                        gyroAngle,
                        modulePositions));

        m_log_offset.log( () -> m_gyroOffset);
    }

    @Override
    public void put(
            double timestampS,
            Pose2d measurement,
            double[] stateSigma,
            double[] visionSigma) {

        // discount the vision update by this factor.
        final double[] k = new double[] {
                mix(Math.pow(stateSigma[0], 2), Math.pow(visionSigma[0], 2)),
                mix(Math.pow(stateSigma[1], 2), Math.pow(visionSigma[1], 2)),
                mix(Math.pow(stateSigma[2], 2), Math.pow(visionSigma[2], 2)) };

        // Step 0: If this measurement is old enough to be outside the pose buffer's
        // timespan, skip.

        if (m_poseBuffer.tooOld(timestampS)) {
            return;
        }

        // Step 1: Get the pose odometry measured at the moment the vision measurement
        // was made.
        InterpolationRecord sample = m_poseBuffer.get(timestampS);

        // Step 2: Measure the twist between the odometry pose and the vision pose.
        Pose2d pose = sample.m_state.pose();
        Twist2d twist = pose.log(measurement);

        // Step 3: We should not trust the twist entirely, so instead we scale this
        // twist by a Kalman gain matrix representing how much we trust vision
        // measurements compared to our current pose.
        // Matrix<N3, N1> k_times_twist = m_visionK.times(VecBuilder.fill(twist.dx,
        // twist.dy, twist.dtheta));

        // Step 4: Convert back to Twist2d.
        Twist2d scaledTwist = new Twist2d(
                k[0] * twist.dx,
                k[1] * twist.dy,
                k[2] * twist.dtheta);
        // Twist2d scaledTwist = new Twist2d(k_times_twist.get(0, 0),
        // k_times_twist.get(1, 0), k_times_twist.get(2, 0));

        Pose2d newPose = sample.m_state.pose().exp(scaledTwist);

        // Step 5: Adjust the gyro offset so that the adjusted pose is consistent with
        // the unadjusted gyro angle
        // this should have no effect if you disregard vision angle input

        m_gyroOffset = newPose.getRotation().minus(sample.m_gyroAngle);
        m_log_offset.log( () -> m_gyroOffset);

        // Step 6: Record the current pose to allow multiple measurements from the same
        // timestamp
        m_poseBuffer.put(
                timestampS,
                new InterpolationRecord(
                        m_kinodynamics.getKinematics(),
                        new SwerveState(newPose, sample.m_state.velocity(), sample.m_state.acceleration()),
                        sample.m_gyroAngle,
                        sample.m_wheelPositions));
        // Step 7: Replay odometry inputs between sample time and latest recorded sample
        // to update the pose buffer and correct odometry.
        // note exclusive tailmap, don't need to reprocess the entry we just put there.
        for (Map.Entry<Double, InterpolationRecord> entry : m_poseBuffer.tailMap(timestampS, false).entrySet()) {
            double entryTimestampS = entry.getKey();
            Rotation2d entryGyroAngle = entry.getValue().m_gyroAngle;
            SwerveModulePosition100[] wheelPositions = entry.getValue().m_wheelPositions;
            put(entryTimestampS, entryGyroAngle, wheelPositions);
        }

    }

    /**
     * Put a new state estimate based on gyro and wheel data. These are expected to
     * be current measurements -- there is no history replay here.
     */
    public void put(
            double currentTimeS,
            Rotation2d gyroAngle,
            SwerveModulePosition100[] wheelPositions) {
        checkLength(wheelPositions);

        List<Entry<Double, InterpolationRecord>> consistentPair = m_poseBuffer.consistentPair(
                currentTimeS, velocityDtS);

        if (consistentPair.isEmpty()) {
            // We're at the beginning. There's nothing to apply the wheel position delta to.
            // This should never happen.
            return;
        }

        // the entry right before this one, the basis for integration.
        Entry<Double, InterpolationRecord> lowerEntry = consistentPair.get(0);

        double t1 = currentTimeS - lowerEntry.getKey();
        InterpolationRecord value = lowerEntry.getValue();
        SwerveState previousPose = value.m_state;

        SwerveModulePosition100[] modulePositionDelta = DriveUtil.modulePositionDelta(
                value.m_wheelPositions,
                wheelPositions);

        Twist2d twist = m_kinodynamics.getKinematics().toTwist2d(modulePositionDelta);

        // replace the twist dtheta with one derived from the current pose
        // pose angle based on the gyro (which is more accurate)

        Rotation2d angle = gyroAngle.plus(m_gyroOffset);
        twist.dtheta = angle.minus(previousPose.pose().getRotation()).getRadians();

        Pose2d newPose = new Pose2d(previousPose.pose().exp(twist).getTranslation(), angle);

        m_log_pose_x.log( newPose::getX);

        FieldRelativeDelta deltaTransform = FieldRelativeDelta.delta(
                previousPose.pose(), newPose).div(t1);
        FieldRelativeVelocity velocity = new FieldRelativeVelocity(
                deltaTransform.getX(),
                deltaTransform.getY(),
                deltaTransform.getRotation().getRadians());

        // calculate acceleration if possible
        FieldRelativeAcceleration accel = new FieldRelativeAcceleration(0, 0, 0);
        if (consistentPair.size() > 1) {
            Map.Entry<Double, InterpolationRecord> earlierEntry = consistentPair.get(1);
            double t0 = lowerEntry.getKey() - earlierEntry.getKey();
            SwerveState earlierPose = earlierEntry.getValue().m_state;
            FieldRelativeDelta earlierTransform = FieldRelativeDelta.delta(
                    earlierPose.pose(), previousPose.pose()).div(t0);
            accel = new FieldRelativeAcceleration(
                    earlierTransform.getX(),
                    earlierTransform.getY(),
                    earlierTransform.getRotation().getRadians());
        }

        SwerveState swerveState = new SwerveState(newPose, velocity, accel);

        m_poseBuffer.put(
                currentTimeS,
                new InterpolationRecord(m_kinodynamics.getKinematics(), swerveState, gyroAngle, wheelPositions));
    }

    ///////////////////////////////////////

    private void checkLength(SwerveModulePosition100[] modulePositions) {
        int ct = modulePositions.length;
        if (ct != m_numModules) {
            throw new IllegalArgumentException("Wrong module count: " + ct);
        }
    }

    /**
     * Given q and r stddev's, what mixture should that yield?
     * This is the "closed form Kalman gain for continuous Kalman filter with A = 0
     * and C = I. See wpimath/algorithms.md." ... but really it's just a mixer.
     */
    private double mix(final double q, final double r) {
        if (q == 0.0)
            return 0.0;
        return q / (q + Math.sqrt(q * r));
    }
}
