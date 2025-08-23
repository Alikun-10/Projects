/**
 * This program implements a graphical user interface (GUI) for a Wordle-style game with 3 difficulty levels, using Java Swing.
 * Players can enter a username, select a difficulty, and attempt to guess words within 6 tries.
 * 
 * @author Adel Abdullatif, Ali Yassine
 * @version 1.6
 */


import javax.swing.*;
import java.awt.*;
import java.awt.event.*;
import java.util.ArrayList;
import java.util.List;
/**
 * The Wordle class represents a graphical implementation of the Wordle game.
 * It uses Java Swing to create a user interface for the game.
 */
public class Wordle extends JFrame {

    private Model backend;
    private JLabel statusLabel;
    private JLabel scoreLabel;
    private JPanel gamePanel;
    private JLabel titleLabel;
    private JLabel[][] labels;
    private int[] currentCell;
    private List<Integer> guesses;
    private boolean gameEnded;
    private int wordLength;
    private static final int TOTAL_GUESSES = 6;
    private boolean instructionsToMain = false;
    private String username;
    private String titleText;
    /**
     * Initializes the Wordle game window, sets up the welcome screen, and other panels.
     */
    public Wordle() {
        super("Wordle");

        titleText = "<html><span style='color:#000;'>W</span>"
                + "<span style='color:#F7D417;'>o</span>"
                + "<span style='color:#85BB65;'>rdle</span></html>";
        guesses = new ArrayList<>();
        gameEnded = false;
        currentCell = new int[] { 0, 0 };

        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setSize(1366, 768);
        setLocationRelativeTo(null);
        setLayout(new CardLayout());

        // Erstelle alle Screens und füge sie zum CardLayout hinzu
        add(createWelcomeScreen(), "welcome"); // Welcome-Screen hinzufügen
        createInstructionsScreen();
        createCreditsScreen();
        createScoreScreen();

        // Zeige zuerst die Username-Eingabeseite
        showUsernamePromptScreen();

        setVisible(true);
    }
    /**
     * Creates the welcome screen with buttons for various game options.
     *
     * @return A JPanel containing the welcome screen components.
     */
    private JPanel createWelcomeScreen() {
        JPanel panel = new JPanel() {
            private Image backgroundImage;

            {
                try {
                    backgroundImage = Toolkit.getDefaultToolkit().createImage("assets/WordleImage.png");
                } catch (Exception e) {
                    System.out.println("Error loading image: " + e.getMessage());
                }
            }

            @Override
            protected void paintComponent(Graphics g) {
                super.paintComponent(g);
                if (backgroundImage != null) {
                    g.drawImage(backgroundImage, 0, 0, getWidth(), getHeight(), this);
                }
            }
        };
        
        panel.setLayout(new BoxLayout(panel, BoxLayout.Y_AXIS));

        JLabel mainTitleLabel = new JLabel(titleText, SwingConstants.CENTER);
        mainTitleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        mainTitleLabel.setForeground(new Color(0x72BB53));
        mainTitleLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        panel.add(Box.createVerticalStrut(50));
        panel.add(mainTitleLabel);
        panel.add(Box.createVerticalStrut(50));
        panel.add(createHomeScreenGrid());
        panel.add(Box.createVerticalStrut(20));

        JButton startButton = createMenuButton("Start");
        startButton.addActionListener(e -> showDifficultySelectionScreen(username));
        panel.add(startButton);
        panel.add(Box.createVerticalStrut(20));

        JButton howToPlayButton = createMenuButton("How to Play");
        howToPlayButton.addActionListener(e -> showInstructions(true));
        panel.add(howToPlayButton);
        panel.add(Box.createVerticalStrut(20));

        JButton scoresButton = createMenuButton("Scores");
        scoresButton.addActionListener(e -> showScoreScreen());
        panel.add(scoresButton);
        panel.add(Box.createVerticalStrut(20));

        JButton creditsButton = createMenuButton("Credits");
        creditsButton.addActionListener(e -> showCreditsScreen());
        panel.add(creditsButton);
        panel.add(Box.createVerticalStrut(20));

        // New "Change Username" Button
        JButton changeUsernameButton = createMenuButton("Change Username");
        changeUsernameButton.addActionListener(e -> {
            CardLayout cl = (CardLayout) getContentPane().getLayout();
            cl.show(getContentPane(), "usernamePrompt");
        });
        panel.add(changeUsernameButton);
        panel.add(Box.createVerticalStrut(20));

        JButton exitButton = createMenuButton("Exit");
        exitButton.addActionListener(e -> System.exit(0));
        panel.add(exitButton);
        panel.add(Box.createVerticalStrut(20));

        return panel;
    }

    /**
     * Creates a button for the menu with standard styling.
     *
     * @param text The text to display on the button.
     * @return A JButton styled for the menu.
     */
    private JButton createMenuButton(String text) {
        JButton button = new JButton(text);
        button.setFont(new Font("Arial", Font.PLAIN, 20));
        button.setBackground(new Color(0xEBEBEB));
        button.setForeground(Color.BLACK);
        button.setBorder(BorderFactory.createLineBorder(Color.BLACK, 1, true));
        button.setFocusPainted(false);
        button.setMaximumSize(new Dimension(200, 50));
        button.setAlignmentX(Component.CENTER_ALIGNMENT);
        return button;
    }
    /**
     * Displays the username prompt screen, where the user can input their username.
     */
    private void showUsernamePromptScreen() {
        JLabel mainTitleLabel = new JLabel(titleText, SwingConstants.CENTER);
        mainTitleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        mainTitleLabel.setForeground(new Color(0x72BB53));
        mainTitleLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JPanel usernamePanel = new JPanel();
        usernamePanel.setLayout(new BoxLayout(usernamePanel, BoxLayout.Y_AXIS));
        usernamePanel.setBackground(new Color(0xFFFFFF));

        JLabel promptLabel = new JLabel("Enter your username:", SwingConstants.CENTER);
        promptLabel.setFont(new Font("Arial", Font.PLAIN, 20));
        promptLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JTextField usernameField = new JTextField();
        usernameField.setMaximumSize(new Dimension(200, 30));
        usernameField.setAlignmentX(Component.CENTER_ALIGNMENT);

        JLabel errorLabel = new JLabel("", SwingConstants.CENTER);
        errorLabel.setFont(new Font("Arial", Font.PLAIN, 16));
        errorLabel.setForeground(Color.RED);
        errorLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JButton submitButton = createMenuButton("Submit");
        submitButton.addActionListener(e -> {
            String username = usernameField.getText().trim();
            if (username.isEmpty()) {
                errorLabel.setText("Username cannot be empty!");
            } else {
                errorLabel.setText(""); // Clear any previous error message
                this.username = username; // Setze den Benutzernamen
                showWelcomeScreen(); // Zeige das Hauptmenü nach der Eingabe
            }
        });

        usernamePanel.add(Box.createVerticalStrut(50));
        usernamePanel.add(mainTitleLabel);
        usernamePanel.add(Box.createVerticalStrut(50));
        usernamePanel.add(createHomeScreenGrid());
        usernamePanel.add(Box.createVerticalStrut(20));
        usernamePanel.add(promptLabel);
        usernamePanel.add(Box.createVerticalStrut(20));
        usernamePanel.add(usernameField);
        usernamePanel.add(Box.createVerticalStrut(20));
        usernamePanel.add(errorLabel);
        usernamePanel.add(Box.createVerticalStrut(20));
        usernamePanel.add(submitButton);

        add(usernamePanel, "usernamePrompt"); // Username-Panel hinzufügen
        CardLayout cl = (CardLayout) getContentPane().getLayout();
        cl.show(getContentPane(), "usernamePrompt"); // Zeige das Username-Panel
    }
    /**
     * Displays the difficulty selection screen for the user.
     * Allows the player to select between Easy, Medium, and Hard modes.
     *
     * @param username The username of the player.
     */
    private void showDifficultySelectionScreen(String username) {
        this.username = username;
        JLabel mainTitleLabel = new JLabel(titleText, SwingConstants.CENTER);
        mainTitleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        mainTitleLabel.setForeground(new Color(0x72BB53));
        mainTitleLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JPanel difficultyPanel = new JPanel();
        difficultyPanel.setLayout(new BoxLayout(difficultyPanel, BoxLayout.Y_AXIS));
        difficultyPanel.setBackground(new Color(0xFFFFFF));

        JLabel welcomeLabel = new JLabel("Welcome, " + username + "!", SwingConstants.CENTER);
        welcomeLabel.setFont(new Font("Arial", Font.PLAIN, 20));
        welcomeLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JButton easyButton = createMenuButton("Easy (4 letters)");
        easyButton.addActionListener(e -> startGame(4));

        JButton mediumButton = createMenuButton("Medium (5 letters)");
        mediumButton.addActionListener(e -> startGame(5));

        JButton hardButton = createMenuButton("Hard (6 letters)");
        hardButton.addActionListener(e -> startGame(6));

        difficultyPanel.add(Box.createVerticalStrut(50));
        difficultyPanel.add(mainTitleLabel);
        difficultyPanel.add(Box.createVerticalStrut(50));
        difficultyPanel.add(welcomeLabel);
        difficultyPanel.add(Box.createVerticalStrut(20));
        difficultyPanel.add(easyButton);
        difficultyPanel.add(Box.createVerticalStrut(20));
        difficultyPanel.add(mediumButton);
        difficultyPanel.add(Box.createVerticalStrut(20));
        difficultyPanel.add(hardButton);

        add(difficultyPanel, "difficultySelection");
        CardLayout cl = (CardLayout) getContentPane().getLayout();
        cl.show(getContentPane(), "difficultySelection");
    }
    /**
     * Starts the game with the selected word length.
     * Initializes the backend model and game screen.
     *
     * @param wordLength The length of the word for the game.
     */
    private void startGame(int wordLength) {
        this.wordLength = wordLength;
        backend = new Model(wordLength, username);
        labels = new JLabel[TOTAL_GUESSES][wordLength];
        createGameScreen();
        showGameScreen();
    }
    /**
     * Displays the game screen.
     * Switches the UI to the game panel.
     */
    private void showGameScreen() {
        // Switch to the game panel
        CardLayout cl = (CardLayout) getContentPane().getLayout();
        cl.show(getContentPane(), "game");
    }
    /**
     * Creates the game screen layout, including the game grid and status label.
     * Initializes UI elements and sets up key listeners.
     */
    private void createGameScreen() {
        JPanel borderPanel = new JPanel(new BorderLayout());
        borderPanel.setBackground(new Color(0xFFFFFF));

        // Top part
        JPanel topPanel = initializeButtons();

        borderPanel.add(topPanel, BorderLayout.NORTH);

        // Center part -> game grid + status
        JPanel centerPanel = new JPanel();
        centerPanel.setLayout(new BoxLayout(centerPanel, BoxLayout.Y_AXIS));
        centerPanel.setBackground(new Color(0xFFFFFF));

        gamePanel = new JPanel(new GridLayout(TOTAL_GUESSES, wordLength, 5, 5));
        gamePanel.setBackground(new Color(0xFFFFFF));
        gamePanel.setMaximumSize(new Dimension(200 + wordLength * 35, 400));
        for (int i = 0; i < TOTAL_GUESSES; i++) {
            for (int j = 0; j < wordLength; j++) {
                JLabel cell = new JLabel("", SwingConstants.CENTER);
                cell.setOpaque(true);
                // cell.setBackground(new Color(0xD8D8D8));
                cell.setBackground(new Color(0xFFFFFF));
                cell.setBorder(BorderFactory.createLineBorder(new Color(0xAAAAAA), 2, true));
                cell.setFont(new Font("Arial", Font.BOLD, 20));
                labels[i][j] = cell;
                gamePanel.add(cell);
            }
        }

        statusLabel = new JLabel("Try guessing a word!");
        statusLabel.setFont(new Font("Arial", Font.PLAIN, 16));
        statusLabel.setAlignmentX(CENTER_ALIGNMENT);

        centerPanel.add(gamePanel);
        centerPanel.add(Box.createVerticalStrut(10));
        centerPanel.add(statusLabel);

        borderPanel.add(centerPanel, BorderLayout.CENTER);

        add(borderPanel, "game");
        addKeyListenerToGame();
        this.setFocusable(true);
        SwingUtilities.invokeLater(() -> this.requestFocusInWindow());

    }
    /**
     * Initializes and returns a JPanel containing UI buttons and the score display.
     * This includes the restart, close, and help buttons.
     *
     * @return A JPanel containing the buttons and the title label.
     */
    private JPanel initializeButtons() {
        JPanel topPanel = new JPanel(new BorderLayout());
        topPanel.setBackground(new Color(0xFFFFFF));

        titleLabel = new JLabel(titleText, SwingConstants.CENTER);
        titleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        titleLabel.setBorder(BorderFactory.createEmptyBorder(0, 80, 0, 0));

        // Buttons
        JButton restartButton = new JButton();
        JButton closeButton = new JButton();
        JButton helpButton = new JButton();

        try {
            Image restartImg = Toolkit.getDefaultToolkit().createImage("assets/restart.png");
            restartButton.setIcon(new ImageIcon(restartImg.getScaledInstance(40, 40, Image.SCALE_SMOOTH)));
            Image closeImg = Toolkit.getDefaultToolkit().createImage("assets/close.png");
            closeButton.setIcon(new ImageIcon(closeImg.getScaledInstance(40, 40, Image.SCALE_SMOOTH)));
            Image helpImg = Toolkit.getDefaultToolkit().createImage("assets/help.png");
            helpButton.setIcon(new ImageIcon(helpImg.getScaledInstance(40, 40, Image.SCALE_SMOOTH)));
        } catch (Exception e) {
            // ignore
        }

        restartButton.setBackground(Color.white);
        restartButton.setForeground(Color.white);
        restartButton.setBorderPainted(false);
        restartButton.setFocusPainted(false);
        restartButton.addActionListener(e -> {
            backend.resetScore();
            scoreLabel.setText("Score: " + backend.getScore());
            restartGame();
        });

        closeButton.setBackground(Color.white);
        closeButton.setForeground(Color.white);
        closeButton.setBorderPainted(false);
        closeButton.setFocusPainted(false);
        closeButton.addActionListener(e -> {
            backend.resetScore();
            showWelcomeScreen();
        });

        helpButton.setBackground(Color.white);
        helpButton.setForeground(Color.white);
        helpButton.setBorderPainted(false);
        helpButton.setFocusPainted(false);
        helpButton.addActionListener(e -> showInstructions(false));

        JPanel leftPanel = new JPanel();
        leftPanel.setBackground(new Color(0xFFFFFF));
        leftPanel.add(helpButton);

        JPanel rightPanel = new JPanel();
        rightPanel.setBackground(new Color(0xFFFFFF));
        rightPanel.add(restartButton);
        rightPanel.add(closeButton);

        topPanel.add(leftPanel, BorderLayout.WEST);
        topPanel.add(titleLabel, BorderLayout.CENTER);
        topPanel.add(rightPanel, BorderLayout.EAST);

        JPanel bottomPanel = new JPanel();
        scoreLabel = new JLabel("Score: " + backend.getScore());
        scoreLabel.setFont(new Font("Arial", Font.BOLD, 16));
        bottomPanel.add(scoreLabel);
        bottomPanel.setBackground(new Color(0xFFFFFF));
        bottomPanel.add(Box.createVerticalStrut(100), BorderLayout.SOUTH);

        topPanel.add(bottomPanel, BorderLayout.SOUTH);
        return topPanel;
    }
    /**
     * Displays the welcome screen, resetting the game if necessary.
     */
    private void showWelcomeScreen() {
        // Reset the game if necessary
        if (backend != null) {
            restartGame();
        }

        // Switch to the welcome panel
        CardLayout cl = (CardLayout) getContentPane().getLayout();
        cl.show(getContentPane(), "welcome"); // Zeige das Welcome-Panel
    }
    /**
     * Creates and displays the instructions screen explaining the game rules.
     */
    private void createInstructionsScreen() {
        JPanel instructionsPanel = new JPanel();
        instructionsPanel.setLayout(new BoxLayout(instructionsPanel, BoxLayout.Y_AXIS));
        instructionsPanel.setBackground(new Color(0xFFFFFF));

        // Title

        JLabel titleLabel = new JLabel(titleText, SwingConstants.CENTER);
        titleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        titleLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JLabel instructionsLabel = new JLabel("<html> <span style='font-size: 20px;'>How to Play</span><br><br>"
                + "Guess the Wordle in 6 tries.<br><br>"
                + "• Each guess must be a valid 6-letter word.<br>"
                + "• The color of the tiles will change to show how close your guess was to the word.<br><br>"
                + "Examples</html>", SwingConstants.CENTER);
        instructionsLabel.setFont(new Font("Arial", Font.PLAIN, 18));
        instructionsLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        // Example cells
        JPanel examplesPanel = new JPanel();
        examplesPanel.setLayout(new BoxLayout(examplesPanel, BoxLayout.Y_AXIS));
        examplesPanel.setBackground(new Color(0xFFFFFF));

        examplesPanel
                .add(createExampleRow("W", "WORDY", "is in the word and in the correct spot.", new Color(0x72BB53)));
        examplesPanel.add(createExampleRow("I", "LIGHT", "is in the word but in the wrong spot.", new Color(0xFFC957)));
        examplesPanel.add(createExampleRow("U", "ROGUE", "is not in the word in any spot.", new Color(0xA0A0A0)));

        // Back button
        JButton backButton = new JButton("< Back");
        backButton.setFont(new Font("Arial", Font.PLAIN, 20));
        backButton.setBackground(new Color(0x72BB53));
        backButton.setForeground(Color.white);
        backButton.setFocusPainted(false);
        backButton.setAlignmentX(Component.CENTER_ALIGNMENT);
        backButton.addActionListener(e -> {
            if (instructionsToMain) {
                showWelcomeScreen();
            } else {
                showGameScreen();
            }
        });

        // Add components to instructions panel
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(titleLabel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(instructionsLabel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(examplesPanel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(backButton);
        instructionsPanel.add(Box.createVerticalStrut(20));

        add(instructionsPanel, "instructions");
    }
    /**
     * Creates and displays the credits screen.
     * This screen contains our names and our group name.
     */
    private void createCreditsScreen() {
        JPanel instructionsPanel = new JPanel();
        instructionsPanel.setLayout(new BoxLayout(instructionsPanel, BoxLayout.Y_AXIS));
        instructionsPanel.setBackground(new Color(0xFFFFFF));

        JLabel titleLabel = new JLabel(titleText, SwingConstants.CENTER);
        titleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        titleLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JLabel instructionsLabel = new JLabel("<html> <span style='font-size: 20px;'>Credits</span><br><br>"
                + "</html>", SwingConstants.CENTER);
        instructionsLabel.setFont(new Font("Arial", Font.BOLD, 18));
        instructionsLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        // Example cells
        JPanel namePanel = new JPanel();
        namePanel.setLayout(new BoxLayout(namePanel, BoxLayout.Y_AXIS));
        namePanel.setBackground(new Color(0xFFFFFF));

        namePanel.add(createNameGrid());

        // Back button
        JButton backButton = new JButton("< Back");
        backButton.setFont(new Font("Arial", Font.PLAIN, 20));
        backButton.setBackground(new Color(0x72BB53));
        backButton.setForeground(Color.white);
        backButton.setFocusPainted(false);
        backButton.setAlignmentX(Component.CENTER_ALIGNMENT);
        backButton.addActionListener(e -> showWelcomeScreen());

        // Add components to instructions panel
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(titleLabel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(instructionsLabel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(namePanel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(backButton);
        instructionsPanel.add(Box.createVerticalStrut(20));

        add(instructionsPanel, "credits");
    }
    /**
     * Creates and displays the score screen.
     * This screen shows the player's scores retrieved from the Model class.
     */
    private void createScoreScreen() {
        JPanel instructionsPanel = new JPanel();
        instructionsPanel.setLayout(new BoxLayout(instructionsPanel, BoxLayout.Y_AXIS));
        instructionsPanel.setBackground(new Color(0xFFFFFF));

        JLabel titleLabel = new JLabel(titleText, SwingConstants.CENTER);
        titleLabel.setFont(new Font("Arial", Font.BOLD, 48));
        titleLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        JLabel instructionsLabel = new JLabel("<html> <span style='font-size: 20px;'>Scores</span><br><br>"
                + "</html>", SwingConstants.CENTER);
        instructionsLabel.setFont(new Font("Arial", Font.BOLD, 18));
        instructionsLabel.setAlignmentX(Component.CENTER_ALIGNMENT);

        // Example cells
        JPanel namePanel = new JPanel();
        namePanel.setLayout(new BoxLayout(namePanel, BoxLayout.Y_AXIS));
        namePanel.setBackground(new Color(0xFFFFFF));

        namePanel.add(createHomeScreenGrid());
        namePanel.add(Box.createVerticalStrut(20));

        List<String> scores = Model.getScores();
        for (String score : scores) {
            String[] parts = score.split(",");
            if (parts.length == 2) {
                String name = parts[0].trim();
                String points = parts[1].trim();

                JPanel rowPanel = new JPanel();
                rowPanel.setLayout(new BoxLayout(rowPanel, BoxLayout.X_AXIS));
                rowPanel.setAlignmentX(Component.CENTER_ALIGNMENT);
                rowPanel.setBorder(BorderFactory.createEmptyBorder(5, 10, 5, 10)); // Add padding
                rowPanel.setMaximumSize(new Dimension(400, 30));
                rowPanel.setBackground(new Color(0xFFFFFF));

                JLabel nameLabel = new JLabel(name, SwingConstants.LEFT);
                nameLabel.setFont(new Font("Arial", Font.PLAIN, 20));
                nameLabel.setPreferredSize(new Dimension(150, 30)); // Set a fixed width for alignment

                JLabel pointsLabel = new JLabel(points, SwingConstants.RIGHT);
                pointsLabel.setFont(new Font("Arial", Font.PLAIN, 20));
                pointsLabel.setPreferredSize(new Dimension(50, 30)); // Set a fixed width for alignment

                rowPanel.add(nameLabel);
                rowPanel.add(Box.createHorizontalGlue()); // Add space between name and points
                rowPanel.add(pointsLabel);
                namePanel.add(rowPanel);
            }
        }
        // Back button
        JButton backButton = new JButton("< Back");
        backButton.setFont(new Font("Arial", Font.PLAIN, 20));
        backButton.setBackground(new Color(0x72BB53));
        backButton.setForeground(Color.white);
        backButton.setFocusPainted(false);
        backButton.setAlignmentX(Component.CENTER_ALIGNMENT);
        backButton.addActionListener(e -> showWelcomeScreen());

        // Add components to instructions panel
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(titleLabel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(instructionsLabel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(namePanel);
        instructionsPanel.add(Box.createVerticalStrut(20));
        instructionsPanel.add(backButton);
        instructionsPanel.add(Box.createVerticalStrut(20));

        add(instructionsPanel, "scores");
    }
    /**
     * Displays the score screen by switching to the "scores" panel.
     * Ensures the screen is refreshed before displaying.
     */
    private void showScoreScreen() {
        // Switch to the scores panel
        CardLayout cl = (CardLayout) getContentPane().getLayout();
        createScoreScreen();
        cl.show(getContentPane(), "scores");
    }

    private JPanel createNameGrid() {
        JPanel gridPanel = new JPanel(new GridLayout(5, 5, 5, 5));
        gridPanel.setBackground(new Color(0xFFFFFF));
        gridPanel.setMaximumSize(new Dimension(370, 400));

        JLabel[][] labels = new JLabel[5][5];
        String[] words = { "ALI  ", "ADEL ", "G-16 ", "SE-24", "  /25" };
        for (int i = 0; i < 5; i++) {
            for (int j = 0; j < 5; j++) {
                JLabel cell = new JLabel("", SwingConstants.CENTER);
                cell.setPreferredSize(new Dimension(5, 60));
                cell.setOpaque(true);
                if ((words[i].charAt(j) != ' ')) {
                    cell.setBackground(new Color(0x72BB53));
                    cell.setBorder(BorderFactory.createLineBorder(new Color(0x72BB53), 2, true));
                } else {
                    cell.setBackground(new Color(0xFFFFFF));
                    cell.setBorder(BorderFactory.createLineBorder(new Color(0xAAAAAA), 2, true));
                }

                cell.setFont(new Font("Arial", Font.PLAIN, 20));
                labels[i][j] = cell;
                cell.setText(Character.toString(words[i].charAt(j)));
                gridPanel.add(cell);
            }
        }

        labels[2][1].setBackground(new Color(0xFFC957));
        labels[2][1].setBorder(BorderFactory.createLineBorder(new Color(0xFFC957), 2, true));
        labels[3][1].setBackground(new Color(0xFFC957));
        labels[3][1].setBorder(BorderFactory.createLineBorder(new Color(0xFFC957), 2, true));
        labels[4][2].setBackground(new Color(0xFFC957));
        labels[4][2].setBorder(BorderFactory.createLineBorder(new Color(0xFFC957), 2, true));
        labels[4][4].setBackground(new Color(0xFFC957));
        labels[4][4].setBorder(BorderFactory.createLineBorder(new Color(0xFFC957), 2, true));

        JPanel namePanel = new JPanel();
        namePanel.setLayout(new BoxLayout(namePanel, BoxLayout.Y_AXIS));
        namePanel.setBackground(new Color(0xFFFFFF));
        namePanel.add(gridPanel);

        return namePanel;
    }

    private JPanel createHomeScreenGrid() {
        JPanel gridPanel = new JPanel(new GridLayout(3, 5, 10, 10));
        gridPanel.setMaximumSize(new Dimension(250, 150));

        JLabel[][] labels = new JLabel[3][5];
        Integer[][] greenIndices = { { 0, 0 }, { 1, 0 }, { 2, 0 }, { 2, 1 }, { 2, 2 }, { 2, 3 } };
        Integer[][] yellowIndices = { { 0, 3 }, { 1, 2 }, { 1, 4 } };

        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 5; j++) {
                JLabel cell = new JLabel("", SwingConstants.CENTER);
                cell.setPreferredSize(new Dimension(5, 60));
                cell.setOpaque(true);
                if (isInArray(greenIndices, i, j)) {
                    cell.setBackground(new Color(0x72BB53));
                    cell.setBorder(BorderFactory.createLineBorder(new Color(0x72BB53), 2, true));
                } else if (isInArray(yellowIndices, i, j)) {
                    cell.setBackground(new Color(0xFFC957));
                    cell.setBorder(BorderFactory.createLineBorder(new Color(0xFFC957), 2, true));
                } else {
                    cell.setBackground(new Color(0xA0A0A0));
                    cell.setBorder(BorderFactory.createLineBorder(new Color(0xAAAAAA), 2, true));
                }

                cell.setFont(new Font("Arial", Font.PLAIN, 20));

                labels[i][j] = cell;
                gridPanel.add(cell);

            }
        }

        JPanel namePanel = new JPanel();
        namePanel.setLayout(new BoxLayout(namePanel, BoxLayout.Y_AXIS));
        namePanel.setBackground(new Color(0xFFFFFF));
        namePanel.add(gridPanel);

        return namePanel;
    }
    /**
     * Checks if the given coordinates (x, y) exist within the provided 2D Integer array.
     *
     * @param arr The 2D Integer array containing coordinate pairs.
     * @param x   The x-coordinate to check.
     * @param y   The y-coordinate to check.
     * @return true if the coordinates exist in the array, false otherwise.
     */
    private boolean isInArray(Integer[][] arr, int x, int y) {
        for (Integer[] pair : arr) {
            if (pair[0] == x && pair[1] == y) {
                return true;
            }
        }
        return false;
    }
    /**
     * Displays the credits screen by switching to the credits panel.
     */
    private void showCreditsScreen() {
        // Switch to the credits panel
        CardLayout cl = (CardLayout) getContentPane().getLayout();
        cl.show(getContentPane(), "credits");
    }
    /**
     * Creates an example row containing a letter, an example word, a description, and a background color.
     *
     * @param letter       The letter to highlight.
     * @param exampleWord  The example word containing the letter.
     * @param description  A description explaining the letter's role in the word.
     * @param bgColor      The background color for highlighted letters.
     * @return A JPanel containing the constructed example row.
     */
    private JPanel createExampleRow(String letter, String exampleWord, String description, Color bgColor) {
        JPanel rowPanel = new JPanel();
        rowPanel.setLayout(new BoxLayout(rowPanel, BoxLayout.X_AXIS));
        rowPanel.setBackground(new Color(0xFFFFFF));

        JLabel letterLabel = new JLabel(letter, SwingConstants.CENTER);
        letterLabel.setPreferredSize(new Dimension(60, 60));
        letterLabel.setOpaque(true);
        letterLabel.setFont(new Font("Arial", Font.BOLD, 20));

        JLabel descriptionLabel = new JLabel(description, SwingConstants.LEFT);
        descriptionLabel.setFont(new Font("Arial", Font.PLAIN, 18));
        descriptionLabel.setAlignmentX(Component.LEFT_ALIGNMENT);

        JPanel gridPanel = new JPanel(new GridLayout(1, exampleWord.length(), 5, 5));
        gridPanel.setBackground(new Color(0xFFFFFF));
        gridPanel.setMaximumSize(new Dimension(330, 130));

        JLabel[] labels = new JLabel[exampleWord.length()];
        for (int i = 0; i < exampleWord.length(); i++) {
            JLabel cell = new JLabel("", SwingConstants.CENTER);
            cell.setPreferredSize(new Dimension(5, 60));
            cell.setOpaque(true);
            // cell.setBackground(new Color(0xD8D8D8));
            if (exampleWord.charAt(i) == letter.charAt(0)) {
                cell.setBackground(bgColor);
                cell.setBorder(BorderFactory.createLineBorder(new Color(bgColor.getRGB()), 2, true));
            } else {
                cell.setBackground(new Color(0xA0A0A0));
                cell.setBorder(BorderFactory.createLineBorder(new Color(0xAAAAAA), 2, true));
            }
            cell.setFont(new Font("Arial", Font.BOLD, 20));
            labels[i] = cell;
            cell.setText(Character.toString(exampleWord.charAt(i)));
            gridPanel.add(cell);

        }
        rowPanel.add(letterLabel);
        rowPanel.add(Box.createHorizontalStrut(10));
        rowPanel.add(descriptionLabel);

        JPanel examplePanel = new JPanel();
        examplePanel.setLayout(new BoxLayout(examplePanel, BoxLayout.Y_AXIS));
        examplePanel.setBackground(new Color(0xFFFFFF));
        examplePanel.add(gridPanel);
        examplePanel.add(rowPanel);

        return examplePanel;
    }
    /**
     * Displays the instructions screen, switching to the instructions panel.
     *
     * @param fromWelcome Indicates if the instructions were accessed from the welcome screen.
     */
    private void showInstructions(boolean fromWelcome) {
        // Switch to the instructions panel
        CardLayout cl = (CardLayout) getContentPane().getLayout();

        cl.show(getContentPane(), "instructions");
        instructionsToMain = fromWelcome;

    }
    /**
     * Adds a key listener to detect user input during the game.
     */
    private void addKeyListenerToGame() {
        // We need focus in the JFrame to detect keys
        for (KeyListener kl : this.getKeyListeners()) {
            this.removeKeyListener(kl);
        }
        this.addKeyListener(new KeyAdapter() {
            @Override
            public void keyPressed(KeyEvent e) {
                if (gameEnded) {
                    return;
                }
                if (e.getKeyCode() == KeyEvent.VK_BACK_SPACE) {
                    if (currentCell[1] > 0) {
                        currentCell[1]--;
                    }
                    labels[currentCell[0]][currentCell[1]].setText("");
                } else if (e.getKeyCode() == KeyEvent.VK_ENTER) {
                    try {
                        String result = backend.check(getGuessFromCurrentRow());
                        colorCellsInCurrentRow(result);
                        if (!gameEnded) {
                            statusLabel.setText("Try guessing a word!");
                        }
                        if (!isLastRow()) {
                            currentCell[0]++;
                            currentCell[1] = 0;
                        }
                    } catch (IllegalArgumentException ex) {
                        statusLabel.setText(ex.getMessage());
                    } catch (Exception ex) {
                        ex.printStackTrace();
                    }
                } else {
                    char keyChar = e.getKeyChar();
                    if (Character.isLetter(keyChar) && currentCell[1] < wordLength) {
                        labels[currentCell[0]][currentCell[1]]
                                .setText(Character.toString(keyChar).toUpperCase());
                        currentCell[1]++;
                    }
                }
            }
        });
    }
    /**
     * Colors the cells in the current row based on the provided result string.
     * 
     * @param result A string representing the coloring pattern ('g' for green, 'y' for yellow, 'i' for incorrect, etc.).
     */
    private void colorCellsInCurrentRow(String result) {
        int colIndex = 0;
        String textColor = "#000000";
        Color borderClr = new Color(0xF5F5F5);
        for (int j = 0; j < wordLength; j++) {
            JLabel cell = labels[currentCell[0]][j];
            char ch = result.charAt(colIndex++);
            Color bg = new Color(0xD8D8D8);
            if (ch == 'g') {
                bg = new Color(0x72BB53);
            } else if (ch == 'y') {
                bg = new Color(0xFFC957);
            } else if (ch == 'i') {
                bg = new Color(0xA0A0A0);
            }
            cell.setOpaque(true);
            cell.setBackground(bg);
            cell.setForeground(Color.decode(textColor));
            cell.setBorder(BorderFactory.createLineBorder(borderClr, 2, true));
        }
        gameEnd(result);
    }
    /**
     * Checks if the game has ended based on the result string.
     * Updates UI messages accordingly.
     * 
     * @param result A string representing the coloring pattern of the row.
     */
    private void gameEnd(String result) {
        boolean allGreen = result.chars().allMatch(c -> c == 'g');
        if (allGreen) {
            statusLabel.setText("You win! Press restart to play again.");
            Thread t = new Thread(() -> {
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
                guesses.add(currentCell[0]);
                backend.incrementScore();
                scoreLabel.setText("Score: " + backend.getScore());
                restartGame();
            });
            t.start();
        } else if (!allGreen && currentCell[0] == TOTAL_GUESSES - 1 && currentCell[1] != 0) {
            statusLabel.setText(
                    "You lose! The correct word was " + backend.getTarget() + ". Press restart to play again.");
            guesses.add(currentCell[0] + 1);
            backend.resetScore();
            scoreLabel.setText("Score: " + backend.getScore());
            gameEnded = true;
        }
    }
    /**
     * Retrieves the guessed word from the current row.
     * 
     * @return The guessed word as a string.
     */
    private String getGuessFromCurrentRow() {
        StringBuilder guess = new StringBuilder();
        for (int j = 0; j < wordLength; j++) {
            guess.append(labels[currentCell[0]][j].getText());
        }
        return guess.toString();
    }
    /**
     * Checks if the current row is the last row of guesses.
     * 
     * @return true if it is the last row, false otherwise.
     */
    private boolean isLastRow() {
        return currentCell[0] == TOTAL_GUESSES - 1;
    }

    /**
     * Resets the game by clearing the board, resetting variables, and setting up a new game.
     */
    
    private void restartGame() {
        for (int i = 0; i < TOTAL_GUESSES; i++) {
            for (int j = 0; j < wordLength; j++) {
                labels[i][j].setText("");
                labels[i][j].setBackground(new Color(0xFFFFFF));
                labels[i][j].setBorder(BorderFactory.createLineBorder(new Color(0xAAAAAA), 2, true));
            }
        }
        currentCell[0] = 0;
        currentCell[1] = 0;
        backend.reset();
        System.out.println("word is " + backend.getTarget());
        statusLabel.setText("Try guessing a word!");
        gameEnded = false;
        this.requestFocus();
    }
    /**
     * Main method to start the game.
     * 
     * @param args Command line arguments.
     */
    public static void main(String[] args) {
        SwingUtilities.invokeLater(Wordle::new);
    }
}