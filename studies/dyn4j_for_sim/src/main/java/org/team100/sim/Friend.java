package org.team100.sim;

import org.dyn4j.dynamics.Force;
import org.dyn4j.geometry.Vector2;
import org.dyn4j.world.World;

/**
 * Foes try to pick from the source and score in the amp corner.
 * 
 * TODO: add two kinds of scoring
 */
public class Friend extends RobotBody {
    private static final int kForce = 200;
    private static final int kTolerance = 2;
    private static final Vector2 kSource = new Vector2(16, 0);
    private static final Vector2 kAmpCorner = new Vector2(0, 8);

    private enum Goal {
        PICK, SCORE
    }

    private final World<Body100> m_world;
    private Goal m_goal;

    public Friend(World<Body100> world) {
        m_world = world;
        // initial goal
        m_goal = Goal.PICK;
    }

    @Override
    public void act() {
        Vector2 position = getWorldCenter();
        Vector2 velocity = getLinearVelocity();
        switch (m_goal) {
            case PICK:
                Vector2 toPick = position.to(kSource);
                if (toPick.getMagnitude() < kTolerance) {
                    // successful pick, now go score
                    m_goal = Goal.SCORE;
                } else {
                    // keep trying
                    applyForce(toPick.setMagnitude(kForce));
                }
                break;
            case SCORE:
                Vector2 toScore = position.to(kAmpCorner);
                if (toScore.getMagnitude() < kTolerance) {
                    // successful score, now go pick
                    m_goal = Goal.PICK;
                } else {
                    // keep trying
                    applyForce(toScore.setMagnitude(kForce));
                }
                break;
        }

        // look for nearby notes, brute force
        for (Body100 body : m_world.getBodies()) {
            if (body instanceof Note) {
                double distance = position.distance(body.getWorldCenter());
                if (distance > 0.3)
                    continue;
                // System.out.printf("%s %5.3f\n",
                // body.getClass().getSimpleName(), distance);
                // TODO: pick up?
            }
        }

        // look for objects in the way
        for (Body100 body : m_world.getBodies()) {
            if (body == this)
                continue;
            Vector2 targetPosition = body.getWorldCenter();
            double distance = position.distance(targetPosition);
            if (distance > 2) // ignore far-away obstacles
                continue;
            if (body instanceof RobotBody || body instanceof Obstacle) {
                Vector2 steer = Geometry.steerToAvoid(
                        position, velocity, targetPosition, 0.5);
                if (steer.getMagnitude() < 1e-3)
                    continue;
                // try very hard
                Vector2 force = steer.product(5000);
                System.out.printf("position %s velocity %s target %s force %s\n",
                        position, velocity, targetPosition, force);
                applyForce(force);
            }
        }

        // avoid the edges of the field
        if (position.x < 1)
            applyForce(new Force(100, 0));
        if (position.x > 15)
            applyForce(new Force(-100, 0));
        if (position.y < 1)
            applyForce(new Force(0, 100));
        if (position.y > 7)
            applyForce(new Force(0, -100));
    }
}
