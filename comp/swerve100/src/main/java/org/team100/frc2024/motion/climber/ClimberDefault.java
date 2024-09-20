package org.team100.frc2024.motion.climber;

import java.util.function.DoubleSupplier;

import org.team100.lib.dashboard.Glassy;
import org.team100.lib.motion.LinearMechanism;
import org.team100.lib.logging.SupplierLogger2;
import org.team100.lib.logging.SupplierLogger2.DoubleSupplierLogger2;
import org.team100.lib.telemetry.Telemetry.Level;

import edu.wpi.first.wpilibj2.command.Command;

public class ClimberDefault extends Command implements Glassy {
    private final SupplierLogger2 m_logger;
    private final ClimberSubsystem m_climber;
    private final DoubleSupplier m_left;
    private final DoubleSupplier m_right;

    // LOGGERS
    private final DoubleSupplierLogger2 m_log_left_manual;
    private final DoubleSupplierLogger2 m_log_right_manual;

    public ClimberDefault(
            SupplierLogger2 logger,
            ClimberSubsystem climber,
            DoubleSupplier leftSupplier,
            DoubleSupplier rightSupplier) {
        m_logger = logger.child(this);
        m_log_left_manual = m_logger.doubleLogger(Level.TRACE, "left manual");
        m_log_right_manual = m_logger.doubleLogger(Level.TRACE, "right manual");
        m_climber = climber;
        m_left = leftSupplier;
        m_right = rightSupplier;
        addRequirements(m_climber);
    }

    @Override
    public void initialize() {
        m_climber.setClimbingForce();
    }

    @Override
    public void execute() {
        manual(m_log_left_manual, m_left, m_climber.getLeft());
        manual(m_log_right_manual, m_right, m_climber.getRight());
    }

    private void manual(
            DoubleSupplierLogger2 log,
            DoubleSupplier inputSupplier,
            LinearMechanism mech) {
        double input = inputSupplier.getAsDouble();
        log.log(() -> input);
        mech.setDutyCycle(input);
    }

    @Override
    public String getGlassName() {
        return "ClimberDefault";
    }
}
