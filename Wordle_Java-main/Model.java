import java.io.File;
import java.io.FileNotFoundException;
import java.io.PrintWriter;
import java.util.*;

/**
 * The Model class represents the game logic for Wordle.
 * It handles word selection, validation, and score management.
 */
public class Model {

    private static final char CORRECT = 'g';
    private static final char MISPLACED = 'y';
    private static final char INCORRECT = 'i';
    private final Random rand;
    private final List<String> words;
    private String target;
    private int wordLength;
    private String username;
    private int score;

    /**
     * Constructs a new Model instance.
     *
     * @param wordLength The length of the target word.
     * @param username   The username of the player.
     */
    public Model(int wordLength, String username) {
        this.wordLength = wordLength;
        words = getWords();
        rand = new Random();
        this.username = username;
        score = 0;
        reset();
    }

    /**
     * Reads the word list from a file and filters words based on length.
     *
     * @return A list of words with the specified length.
     */
    private List<String> getWords() {
        List<String> lines = new ArrayList<>();
        File file = new File("words.txt");
        try (Scanner scan = new Scanner(file)) {
            while (scan.hasNextLine()) {
                String line = scan.nextLine();
                if (line.length() == wordLength) {
                    lines.add(line.toLowerCase());
                }
            }
        } catch (FileNotFoundException fnfe) {
            System.out.println("Error reading words.txt: " + fnfe.getMessage());
        }
        return lines;
    }

    /**
     * Resets the game by selecting a new target word randomly.
     */
    public void reset() {
        target = words.get(rand.nextInt(words.size()));
        System.out.println("Target: " + target);
    }

    /**
     * Checks the user's guessed word against the target word.
     *
     * @param word The guessed word.
     * @return A string representing the correctness of each letter ('g' for correct, 'y' for misplaced, 'i' for incorrect).
     * @throws IllegalArgumentException If the word is invalid or not in the word list.
     */
    public String check(String word) throws IllegalArgumentException {
        if (word == null || word.length() != wordLength || word.isBlank()) {
            throw new IllegalArgumentException("Invalid word length.");
        }
        if (!words.contains(word.toLowerCase())) {
            throw new IllegalArgumentException("Invalid word.");
        }
        word = word.toLowerCase();
        char[] targetArray = target.toCharArray();
        char[] result = new char[wordLength];

        Arrays.fill(result, INCORRECT);

        for (int i = 0; i < wordLength; i++) {
            if (word.charAt(i) == targetArray[i]) {
                result[i] = CORRECT;
                targetArray[i] = 0;
            }
        }

        for (int i = 0; i < wordLength; i++) {
            if (result[i] == INCORRECT) {
                for (int j = 0; j < wordLength; j++) {
                    if (word.charAt(i) == targetArray[j]) {
                        result[i] = MISPLACED;
                        targetArray[j] = 0;
                        break;
                    }
                }
            }
        }

        return String.valueOf(result);
    }

    /**
     * Gets the target word for the current game session.
     *
     * @return The target word.
     */
    public String getTarget() {
        return target;
    }

    /**
     * Gets the player's current score.
     *
     * @return The score.
     */
    public int getScore() {
        return score;
    }

    /**
     * Increments the player's score and updates the score file.
     */
    public void incrementScore() {
        score++;
        updateScoreFile();
    }

    /**
     * Resets the player's score and updates the score file.
     */
    public void resetScore() {
        score = 0;
        updateScoreFile();
    }

    /**
     * Updates the score file with the highest score for each player.
     * Ranks the top 10 scores from highest to lowest.
     */
    public void updateScoreFile() {
        File file = new File("scores.txt");
        Map<String, Integer> scoreMap = new HashMap<>();

        // Read existing scores
        try (Scanner scan = new Scanner(file)) {
            while (scan.hasNextLine()) {
                String[] parts = scan.nextLine().split(",");
                if (parts.length == 2) {
                    String player = parts[0].trim();
                    int highScore = Integer.parseInt(parts[1].trim());
                    scoreMap.put(player, Math.max(scoreMap.getOrDefault(player, 0), highScore));
                }
            }
        } catch (FileNotFoundException fnfe) {
            System.out.println("Error reading scores.txt: " + fnfe.getMessage());
        }

        // Update score only if it's higher
        scoreMap.put(username, Math.max(scoreMap.getOrDefault(username, 0), score));

        // Sort by score in descending order
        List<Map.Entry<String, Integer>> sortedScores = new ArrayList<>(scoreMap.entrySet());
        sortedScores.sort((a, b) -> Integer.compare(b.getValue(), a.getValue()));

        // Keep only the top 10 scores
        List<String> topScores = new ArrayList<>();
        for (int i = 0; i < Math.min(10, sortedScores.size()); i++) {
            Map.Entry<String, Integer> entry = sortedScores.get(i);
            topScores.add(entry.getKey() + "," + entry.getValue());
        }

        // Write updated scores to file
        try (PrintWriter writer = new PrintWriter(file)) {
            for (String scoreEntry : topScores) {
                writer.println(scoreEntry);
            }
        } catch (FileNotFoundException fnfe) {
            System.out.println("Error writing scores.txt: " + fnfe.getMessage());
        }
    }

    /**
     * Retrieves the list of top 10 player scores from the score file.
     *
     * @return A list of scores in string format.
     */
    public static List<String> getScores() {
        List<String> scores = new ArrayList<>();
        File file = new File("scores.txt");
        try (Scanner scan = new Scanner(file)) {
            while (scan.hasNextLine()) {
                scores.add(scan.nextLine());
            }
        } catch (FileNotFoundException fnfe) {
            System.out.println("Error reading scores.txt: " + fnfe.getMessage());
        }
        return scores;
    }
}

