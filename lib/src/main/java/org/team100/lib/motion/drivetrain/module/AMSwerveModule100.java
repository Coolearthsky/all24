package org.team100.lib.motion.drivetrain.module;

import org.team100.lib.config.Feedforward100;
import org.team100.lib.config.PIDConstants;
import org.team100.lib.encoder.AnalogTurningEncoder;
import org.team100.lib.encoder.EncoderDrive;
import org.team100.lib.encoder.Talon6Encoder;
import org.team100.lib.encoder.VelocityBareEncoder;
import org.team100.lib.framework.TimedRobot100;
import org.team100.lib.logging.LoggerFactory;
import org.team100.lib.motion.drivetrain.kinodynamics.SwerveKinodynamics;
import org.team100.lib.motion.mechanism.LinearMechanism;
import org.team100.lib.motion.mechanism.RotaryMechanism;
import org.team100.lib.motion.mechanism.SimpleLinearMechanism;
import org.team100.lib.motion.mechanism.SimpleRotaryMechanism;
import org.team100.lib.motion.servo.AngularPositionServo;
import org.team100.lib.motion.servo.LinearVelocityServo;
import org.team100.lib.motion.servo.OnboardAngularPositionServo;
import org.team100.lib.motion.servo.OutboardLinearVelocityServo;
import org.team100.lib.motor.BareMotorController100;
import org.team100.lib.motor.Falcon6Motor;
import org.team100.lib.motor.MotorPhase;
import org.team100.lib.profile.Profile100;

import edu.wpi.first.math.controller.PIDController;
import edu.wpi.first.wpilibj.motorcontrol.VictorSP;

/**
 * Stock AndyMark module with Falcon drive and PWM 775 steering.
 * 
 * 
 */
public class AMSwerveModule100 extends SwerveModule100 {
    /**
     * There is a planetary gearbox between the motor and the steering gear, and the
     * final is 48/40.
     */
    private static final double kSteeringReduction = 71.0 * 40 / 48;
    // AndyMark Swerve & Steer has 4 inch wheel: this number is more like 3.75
    // inches which represents a significantly worn wheel.
    private static final double kWheelDiameterM = 0.09628;
    // see andymark.com/products/swerve-and-steer
    private static final double kDriveReduction = 6.67;

    /** @param name like "front left" or whatever */
    public static AMSwerveModule100 get(
            LoggerFactory parent,
            double currentLimit,
            double statorLimit,
            int driveMotorCanId,
            int turningMotorChannel,
            int turningEncoderChannel,
            double turningOffset,
            SwerveKinodynamics kinodynamics,
            PIDConstants pidConstants,
            Feedforward100 ff) {
        LinearVelocityServo driveServo = driveServo(
                parent.child("Drive"),
                currentLimit,
                statorLimit,
                driveMotorCanId,
                pidConstants,
                ff);

        AngularPositionServo turningServo = turningServo(
                parent.child("Turning"),
                turningMotorChannel,
                turningEncoderChannel,
                turningOffset,
                kinodynamics);

        return new AMSwerveModule100(driveServo, turningServo);
    }

    private static LinearVelocityServo driveServo(
            LoggerFactory parent,
            double currentLimit,
            double statorLimit,
            int driveMotorCanId,
            PIDConstants pidConstants,
            Feedforward100 ff) {
        Falcon6Motor driveMotor = new Falcon6Motor(
                parent,
                driveMotorCanId,
                MotorPhase.FORWARD,
                currentLimit,
                statorLimit,
                pidConstants,
                ff);
        LinearMechanism mech = new SimpleLinearMechanism(
                driveMotor,
                new Talon6Encoder(parent, driveMotor),
                kDriveReduction,
                kWheelDiameterM);
        return new OutboardLinearVelocityServo(
                parent,
                mech);
    }

    private static AngularPositionServo turningServo(
            LoggerFactory parent,
            int turningMotorChannel,
            int turningEncoderChannel,
            double turningOffset,
            SwerveKinodynamics kinodynamics) {
        BareMotorController100 turningMotor = new BareMotorController100(
                parent,
                new VictorSP(turningMotorChannel));
        RotaryMechanism steeringGears = new SimpleRotaryMechanism(
                parent,
                turningMotor,
                new VelocityBareEncoder(parent, turningMotor),
                kSteeringReduction);
        AnalogTurningEncoder turningEncoder = new AnalogTurningEncoder(
                parent,
                turningEncoderChannel,
                turningOffset,
                EncoderDrive.DIRECT);

        PIDController turningPositionController = new PIDController(
                0.5, // kP
                0, // kI
                0, // kD
                TimedRobot100.LOOP_PERIOD_S);
        turningPositionController.enableContinuousInput(-Math.PI, Math.PI);
        turningPositionController.setTolerance(0.1, 0.1);
        Profile100 profile = kinodynamics.getSteeringProfile();
        OnboardAngularPositionServo turningServo = new OnboardAngularPositionServo(
                parent,
                steeringGears,
                turningEncoder,
                kinodynamics.getMaxSteeringVelocityRad_S(),
                turningPositionController);
        turningServo.setProfile(profile);
        turningServo.reset();
        return turningServo;
    }

    private AMSwerveModule100(
            LinearVelocityServo driveServo,
            AngularPositionServo turningServo) {
        super(driveServo, turningServo);
        //
    }

}
