package org.team100.lib.pilot;

import java.util.function.BooleanSupplier;
import java.util.function.Predicate;
import java.util.function.Supplier;

import org.team100.lib.util.Arg;

import edu.wpi.first.math.geometry.Pose2d;

/**
 * Cycle from source to amp and back
 */
public class AmpCycler extends AutoPilot {
    private final Supplier<Pose2d> m_drive;
    private final Predicate<Pose2d> m_camera;
    private final BooleanSupplier m_indexer;

    public AmpCycler(
            Supplier<Pose2d> drive,
            Predicate<Pose2d> camera,
            BooleanSupplier indexer) {
        Arg.nonnull(drive);
        Arg.nonnull(camera);
        Arg.nonnull(indexer);
        m_drive = drive;
        m_camera = camera;
        m_indexer = indexer;
    }

    @Override
    public boolean scoreAmp() {
        return enabled() && m_indexer.getAsBoolean();
    }

    @Override
    public boolean driveToSource() {
        return enabled() && !m_camera.test(m_drive.get()) && !m_indexer.getAsBoolean();
    }

    @Override
    public boolean intake() {
        return enabled() && m_camera.test(m_drive.get()) && !m_indexer.getAsBoolean();
    }

    @Override
    public boolean driveToNote() {
        return enabled() && m_camera.test(m_drive.get()) && !m_indexer.getAsBoolean();
    }
}
