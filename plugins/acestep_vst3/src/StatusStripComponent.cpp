#include "StatusStripComponent.h"

#include "V2Chrome.h"

namespace acestep::vst3
{
StatusStripComponent::StatusStripComponent()
{
    brandLabel_.setText("ACE-STEP // TAPE SYNTH", juce::dontSendNotification);
    brandLabel_.setFont(juce::Font(juce::FontOptions(28.0f, juce::Font::bold)));
    brandLabel_.setColour(juce::Label::textColourId, v2::kLabelPrimary);
    sessionLabel_.setColour(juce::Label::textColourId, v2::kLabelMuted);
    modeLabel_.setColour(juce::Label::textColourId, v2::kAccentMint);
    backendLabel_.setColour(juce::Label::textColourId, v2::kLabelPrimary);

    for (auto* label : {&brandLabel_, &sessionLabel_, &modeLabel_, &backendLabel_})
    {
        label->setJustificationType(juce::Justification::centredLeft);
        addAndMakeVisible(*label);
    }
}

void StatusStripComponent::paint(juce::Graphics& g)
{
    auto bounds = getLocalBounds();
    v2::drawModule(g, bounds, "Status Strip", v2::kAccentBlue);
    auto lamp = juce::Rectangle<float>(18.0f, 18.0f)
                    .withCentre({static_cast<float>(bounds.getRight() - 32), static_cast<float>(bounds.getY() + 32)});
    v2::drawLamp(g, lamp, v2::statusColour(backendStatus_), backendStatus_ == BackendStatus::ready);
}

void StatusStripComponent::resized()
{
    auto area = getLocalBounds().reduced(18, 12);
    auto top = area.removeFromTop(28);
    brandLabel_.setBounds(top.removeFromLeft(area.getWidth() / 2 + 120));
    modeLabel_.setBounds(top.removeFromLeft(180));
    backendLabel_.setBounds(top.removeFromLeft(190));
    sessionLabel_.setBounds(area.removeFromTop(20));
}

void StatusStripComponent::setSessionName(const juce::String& sessionName)
{
    sessionLabel_.setText(sessionName, juce::dontSendNotification);
}

void StatusStripComponent::setModeName(const juce::String& modeName)
{
    modeLabel_.setText(modeName, juce::dontSendNotification);
}

void StatusStripComponent::setBackendStatus(BackendStatus status)
{
    backendStatus_ = status;
    backendLabel_.setText("BACKEND " + toString(status).toUpperCase(), juce::dontSendNotification);
    repaint();
}
}  // namespace acestep::vst3
