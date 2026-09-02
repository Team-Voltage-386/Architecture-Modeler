package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** AprilTag-based targeting camera. Not yet reflected in the design model. */
public class Vision extends SubsystemBase {
  private final PhotonCamera camera = new PhotonCamera("front");
}
