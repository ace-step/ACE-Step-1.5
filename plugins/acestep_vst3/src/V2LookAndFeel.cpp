#include "V2LookAndFeel.h"

#include "V2Chrome.h"

namespace acestep::vst3
{
V2LookAndFeel::V2LookAndFeel()
{
    setColour(juce::Label::textColourId, v2::kLabelPrimary);
    setColour(juce::TextEditor::backgroundColourId, v2::kModuleFill.brighter(0.06f));
    setColour(juce::TextEditor::outlineColourId, v2::kModuleStroke);
    setColour(juce::TextEditor::focusedOutlineColourId, v2::kAccentMint);
    setColour(juce::TextEditor::textColourId, v2::kLabelPrimary);
    setColour(juce::TextEditor::highlightColourId, v2::kAccentBlue.withAlpha(0.24f));
    setColour(juce::CaretComponent::caretColourId, v2::kAccentMint);
    setColour(juce::ComboBox::backgroundColourId, v2::kModuleFill);
    setColour(juce::ComboBox::outlineColourId, v2::kModuleStroke);
    setColour(juce::ComboBox::arrowColourId, v2::kLabelMuted);
    setColour(juce::ComboBox::textColourId, v2::kLabelPrimary);
    setColour(juce::ToggleButton::textColourId, v2::kLabelPrimary);
    setColour(juce::PopupMenu::backgroundColourId, v2::kModuleFill);
    setColour(juce::PopupMenu::textColourId, v2::kLabelPrimary);
}

juce::Font V2LookAndFeel::getTextButtonFont(juce::TextButton&, int buttonHeight)
{
    return juce::Font(
        juce::FontOptions(static_cast<float>(juce::jmin(18, buttonHeight / 2 + 4)), juce::Font::bold));
}

juce::Font V2LookAndFeel::getComboBoxFont(juce::ComboBox& box)
{
    return juce::Font(
        juce::FontOptions(static_cast<float>(juce::jmin(17, box.getHeight() / 2 + 2)), juce::Font::plain));
}

void V2LookAndFeel::drawButtonBackground(juce::Graphics& g,
                                         juce::Button& button,
                                         const juce::Colour&,
                                         bool isMouseOverButton,
                                         bool isButtonDown)
{
    auto bounds = button.getLocalBounds().toFloat().reduced(0.5f);
    auto fill = button.getButtonText().containsIgnoreCase("render")
                    || button.getButtonText().containsIgnoreCase("generate")
                    ? v2::kAccentAmber
                    : v2::kModuleRaised;
    if (!button.isEnabled())
    {
        fill = fill.darker(0.65f);
    }
    if (isMouseOverButton)
    {
        fill = fill.brighter(0.14f);
    }
    if (isButtonDown)
    {
        fill = fill.darker(0.2f);
    }

    g.setGradientFill(juce::ColourGradient(fill.brighter(0.08f), bounds.getTopLeft(), fill.darker(0.24f), bounds.getBottomLeft(), false));
    g.fillRoundedRectangle(bounds, 10.0f);
    g.setColour(juce::Colours::black.withAlpha(0.35f));
    g.drawRoundedRectangle(bounds.translated(0.0f, 1.0f), 10.0f, 1.8f);
    g.setColour(v2::kModuleStroke.withAlpha(0.9f));
    g.drawRoundedRectangle(bounds, 10.0f, 1.0f);
}

void V2LookAndFeel::drawComboBox(juce::Graphics& g,
                                 int width,
                                 int height,
                                 bool,
                                 int,
                                 int,
                                 int,
                                 int,
                                 juce::ComboBox& box)
{
    auto bounds = juce::Rectangle<float>(0.0f, 0.0f, static_cast<float>(width), static_cast<float>(height))
                      .reduced(0.5f);
    g.setGradientFill(juce::ColourGradient(v2::kModuleRaised, bounds.getTopLeft(), v2::kModuleFill, bounds.getBottomLeft(), false));
    g.fillRoundedRectangle(bounds, 10.0f);
    g.setColour(v2::kModuleStroke);
    g.drawRoundedRectangle(bounds, 10.0f, 1.0f);

    auto arrowZone = bounds.removeFromRight(28.0f).reduced(6.0f, 9.0f);
    juce::Path arrow;
    arrow.startNewSubPath(arrowZone.getX(), arrowZone.getY());
    arrow.lineTo(arrowZone.getCentreX(), arrowZone.getBottom());
    arrow.lineTo(arrowZone.getRight(), arrowZone.getY());
    g.setColour(box.isEnabled() ? v2::kAccentMint : v2::kLabelMuted);
    g.strokePath(arrow, juce::PathStrokeType(1.8f));
}

void V2LookAndFeel::drawTextEditorOutline(juce::Graphics& g,
                                          int width,
                                          int height,
                                          juce::TextEditor& textEditor)
{
    auto bounds = juce::Rectangle<float>(0.0f, 0.0f, static_cast<float>(width), static_cast<float>(height))
                      .reduced(0.5f);
    g.setColour(juce::Colours::black.withAlpha(0.35f));
    g.drawRoundedRectangle(bounds.translated(0.0f, 1.0f), 10.0f, 1.6f);
    g.setColour(textEditor.hasKeyboardFocus(true) ? v2::kAccentMint : v2::kModuleStroke);
    g.drawRoundedRectangle(bounds, 10.0f, textEditor.hasKeyboardFocus(true) ? 1.3f : 1.0f);
}

void V2LookAndFeel::drawToggleButton(juce::Graphics& g,
                                     juce::ToggleButton& button,
                                     bool isMouseOverButton,
                                     bool isButtonDown)
{
    auto bounds = button.getLocalBounds().toFloat().reduced(0.5f);
    auto active = button.getToggleState();
    auto fill = active ? v2::kAccentMint.withAlpha(0.22f) : v2::kModuleRaised;
    if (isMouseOverButton)
    {
        fill = fill.brighter(0.08f);
    }
    if (isButtonDown)
    {
        fill = fill.darker(0.14f);
    }

    g.setGradientFill(juce::ColourGradient(fill.brighter(0.06f),
                                           bounds.getTopLeft(),
                                           fill.darker(0.22f),
                                           bounds.getBottomLeft(),
                                           false));
    g.fillRoundedRectangle(bounds, 11.0f);
    g.setColour(active ? v2::kAccentMint : v2::kModuleStroke);
    g.drawRoundedRectangle(bounds, 11.0f, active ? 1.6f : 1.0f);

    auto lampBounds = juce::Rectangle<float>(18.0f, 18.0f)
                          .withCentre({bounds.getX() + 18.0f, bounds.getCentreY()});
    v2::drawLamp(g, lampBounds, v2::kAccentMint, active);

    g.setColour(v2::kLabelPrimary);
    g.setFont(juce::Font(juce::FontOptions(13.5f, juce::Font::bold)));
    g.drawText(button.getButtonText(),
               bounds.reduced(34.0f, 0.0f).toNearestInt(),
               juce::Justification::centredLeft);
}
}  // namespace acestep::vst3
