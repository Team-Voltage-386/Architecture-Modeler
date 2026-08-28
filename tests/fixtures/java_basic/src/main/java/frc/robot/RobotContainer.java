package frc.robot;

public class RobotContainer {
  private final Controller driver = new Controller();

  public RobotContainer(Drive drive) {
    driver.a().onTrue(new DriveCommand(drive));
  }
}
