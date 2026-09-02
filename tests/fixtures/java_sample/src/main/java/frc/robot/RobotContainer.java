package frc.robot;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj.smartdashboard.SendableChooser;
import frc.robot.commands.Climb;
import frc.robot.commands.LowerElevator;
import frc.robot.commands.RaiseElevator;
import frc.robot.commands.RunIntake;
import frc.robot.commands.RunShooter;
import frc.robot.commands.ScoreAndLeave;
import frc.robot.commands.TeleopDrive;
import frc.robot.subsystems.ClimberSubsystem;
import frc.robot.subsystems.Drivetrain;
import frc.robot.subsystems.Elevator;
import frc.robot.subsystems.Intake;
import frc.robot.subsystems.Shooter;
import frc.robot.subsystems.Vision;

public class RobotContainer {
  private final Drivetrain drivetrain = new Drivetrain();
  private final Intake intake = new Intake();
  private final Elevator elevator = new Elevator();
  private final Shooter shooter = new Shooter();
  private final ClimberSubsystem climber = new ClimberSubsystem();
  private final Vision vision = new Vision();

  private final Controller driver = new Controller();
  private final Controller operator = new Controller();
  private final SendableChooser<Command> chooser = new SendableChooser<>();

  public RobotContainer() {
    drivetrain.setDefaultCommand(new TeleopDrive(drivetrain));

    operator.rightTrigger().whileTrue(new RunIntake(intake));
    operator.y().onTrue(new RaiseElevator(elevator));
    operator.a().onTrue(new LowerElevator(elevator));
    operator.rightBumper().whileTrue(new RunShooter(shooter));
    operator.start().whileTrue(new Climb(climber));

    chooser.addOption("Score and Leave", new ScoreAndLeave(drivetrain, shooter));
  }
}
