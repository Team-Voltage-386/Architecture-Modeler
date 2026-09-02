package frc.robot.commands;

import edu.wpi.first.wpilibj2.command.CommandBase;
import frc.robot.subsystems.Drivetrain;
import frc.robot.subsystems.Shooter;

/** Autonomous routine: score the preloaded game piece, then drive out of the starting zone. */
public class ScoreAndLeave extends CommandBase {
  private final Drivetrain drivetrain;
  private final Shooter shooter;

  public ScoreAndLeave(Drivetrain drivetrain, Shooter shooter) {
    this.drivetrain = drivetrain;
    this.shooter = shooter;
    addRequirements(drivetrain, shooter);
  }

  @Override
  public void initialize() {}

  @Override
  public void execute() {}

  @Override
  public boolean isFinished() {
    return false;
  }

  @Override
  public void end(boolean interrupted) {}
}
