package org.team100.lib.localization;

import java.util.Arrays;
import java.util.Objects;

import org.team100.lib.motion.drivetrain.SwerveState;
import org.team100.lib.motion.drivetrain.kinodynamics.SwerveDriveKinematics100;
import org.team100.lib.motion.drivetrain.kinodynamics.SwerveModulePosition100;
import org.team100.lib.util.DriveUtil;

import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Twist2d;
import edu.wpi.first.math.interpolation.Interpolatable;

/**
 * Represents an odometry record. The record contains the inputs provided as
 * well as the pose that was observed based on these inputs, as well as the
 * previous record and its inputs.
 * 
 * TODO: add velocity and acceleration.
 */
class InterpolationRecord implements Interpolatable<InterpolationRecord> {
    private final SwerveDriveKinematics100 m_kinematics;

    // The pose observed given the current sensor inputs and the previous pose.
    final SwerveState m_state;

    // The current gyro angle.
    final Rotation2d m_gyroAngle;

    // The current encoder readings.
    final SwerveModulePosition100[] m_wheelPositions;

    /**
     * Constructs an Interpolation Record with the specified parameters.
     *
     * @param state          The pose observed given the current sensor inputs and
     *                       the previous pose.
     * @param gyro           The current gyro angle.
     * @param wheelPositions The current encoder readings. Makes a copy.
     */
    InterpolationRecord(
            SwerveDriveKinematics100 kinematics,
            SwerveState state,
            Rotation2d gyro,
            SwerveModulePosition100[] wheelPositions) {
        m_kinematics = kinematics;
        m_state = state;
        m_gyroAngle = gyro;
        m_wheelPositions = new SwerveModulePosition100[wheelPositions.length];
        for (int i = 0; i < wheelPositions.length; ++i) {
            m_wheelPositions[i] = wheelPositions[i].copy();
        }
    }

    /**
     * Return the "interpolated" record. This object is assumed to be the starting
     * position, or lower bound.
     * 
     * Interpolates the wheel positions.
     * Interpolates the gyro angle.
     * ***INTEGRATES*** to find the pose; ignores the supplied end pose unless t >=
     * 1 :-(.
     *
     * @param endValue The upper bound, or end.
     * @param t        How far between the lower and upper bound we are. This should
     *                 be bounded in [0, 1].
     * @return The interpolated value.
     */
    @Override
    public InterpolationRecord interpolate(InterpolationRecord endValue, double t) {
        if (t < 0) {
            return this;
        }
        if (t >= 1) {
            return endValue;
        }
        // Find the new wheel distances.
        SwerveModulePosition100[] wheelLerp = new SwerveModulePosition100[m_wheelPositions.length];
        for (int i = 0; i < m_wheelPositions.length; ++i) {
            wheelLerp[i] = m_wheelPositions[i].interpolate(endValue.m_wheelPositions[i], t);
        }

        // Find the new gyro angle.
        Rotation2d gyroLerp = m_gyroAngle.interpolate(endValue.m_gyroAngle, t);

        // Create a twist to represent the change based on the interpolated sensor
        // inputs.
        Twist2d twist = m_kinematics.toTwist2d(
                DriveUtil.modulePositionDelta(m_wheelPositions, wheelLerp));
        twist.dtheta = gyroLerp.minus(m_gyroAngle).getRadians();

        SwerveState newState = new SwerveState(
                m_state.pose().exp(twist),
                m_state.velocity(),
                m_state.acceleration());
        return new InterpolationRecord(m_kinematics, newState, gyroLerp, wheelLerp);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof InterpolationRecord)) {
            return false;
        }
        InterpolationRecord rec = (InterpolationRecord) obj;
        return Objects.equals(m_gyroAngle, rec.m_gyroAngle)
                && Objects.equals(m_wheelPositions, rec.m_wheelPositions)
                && Objects.equals(m_state, rec.m_state);
    }

    @Override
    public int hashCode() {
        return Objects.hash(m_gyroAngle, m_wheelPositions, m_state);
    }

    @Override
    public String toString() {
        return "InterpolationRecord [m_poseMeters=" + m_state + ", m_gyroAngle=" + m_gyroAngle
                + ", m_wheelPositions=" + Arrays.toString(m_wheelPositions) + "]";
    }

}