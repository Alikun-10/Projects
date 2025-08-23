import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ModelCheckTest {
    private Model model;

    @BeforeEach
    void setUp() {
        model = new Model(5, "testUser"); // Wortlänge 5 für die Tests
    }

    @Test
    void testCheck_CorrectWord() {
        model.reset();
        String target = model.getTarget();
        assertEquals("ggggg", model.check(target), "Das Zielwort sollte vollständig korrekt sein.");
    }

    @Test
    void testCheck_WrongLength() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            model.check("word"); // Zu kurzes Wort
        });
        assertEquals("Invalid word length.", exception.getMessage());
    }

    @Test
    void testCheck_WordNotInList() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            model.check("xxxxx"); // Wort existiert nicht
        });
        assertEquals("Invalid word.", exception.getMessage());
    }

    @Test
    void testCheck_MisplacedLetters() {
        model.reset();
        String target = model.getTarget();
        if (target.length() != 5) {
            String shuffled = new StringBuilder(target).reverse().toString();
            assertEquals("yyyyy", model.check(shuffled), "Alle Buchstaben sind enthalten, aber falsch platziert.");
        }
    }

    @Test
    void testCheck_TooLongWord() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            model.check("longword"); // Zu langes Wort
        });
        assertEquals("Invalid word length.", exception.getMessage());
    }

    @Test
    void testCheck_TooShortWord() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            model.check("hi"); // Zu kurzes Wort
        });
        assertEquals("Invalid word length.", exception.getMessage());
    }

    @Test
    void testCheck_EmptyInput() {
        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            model.check(""); // Leere Eingabe
        });
        assertEquals("Invalid word length.", exception.getMessage());
    }
}
